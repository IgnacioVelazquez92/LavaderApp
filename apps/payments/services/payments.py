# apps/payments/services/payments.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional, List

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.payments.models import Pago, MedioPago
from apps.sales.services import sales as sales_services


class OverpayNeedsConfirmation(Exception):
    """Se intentó pagar más que el saldo. Requiere confirmación para registrar la diferencia como propina."""

    def __init__(self, *, saldo: Decimal, monto: Decimal):
        self.saldo = saldo or Decimal("0.00")
        self.monto = monto or Decimal("0.00")
        self.diferencia = self.monto - self.saldo
        super().__init__(
            f"Sobrepago: monto={self.monto} > saldo={self.saldo}. Diferencia={self.diferencia}.")


@transaction.atomic
def registrar_pago(
    *,
    venta,
    medio: MedioPago,
    monto: Decimal,
    es_propina: bool,
    referencia: Optional[str],
    notas: Optional[str],
    creado_por,
    idempotency_key: Optional[str] = None,
    auto_split_propina: bool = False,
) -> List[Pago]:
    """
    Registra pago(s) para una venta.

    Reglas:
      - monto > 0
      - medio.empresa == venta.empresa (tenant)
      - Si es_propina=True → registra (no descuenta saldo).
      - Si es_propina=False y monto <= saldo → registra (descuenta saldo).
      - Si es_propina=False y monto > saldo:
          - auto_split_propina=False → levanta OverpayNeedsConfirmation (para que la vista pregunte).
          - auto_split_propina=True  → crea 2 Pagos: saldo (no propina) + diferencia (propina).
      - Idempotencia opcional por (venta, idempotency_key). En split se generan dos claves derivadas.
      - Tras registrar, se recalcula saldo y si queda en 0 → venta pasa a 'pagado'.
    """
    # Lock fuerte sobre la venta para consistencia de saldo y evitar condiciones de carrera.
    type(venta).objects.select_for_update().filter(pk=venta.pk).exists()

    # Normalizaciones
    es_propina = bool(es_propina)
    referencia = referencia or ""
    notas = notas or ""

    # monto > 0
    if monto is None or monto <= 0:
        raise ValidationError(_("El monto del pago debe ser mayor a 0."))

    # Tenant: el medio debe pertenecer a la misma empresa que la venta
    if medio.empresa_id != venta.empresa_id:
        raise ValidationError(
            _("El medio de pago no pertenece a la empresa de la venta."))

    # Idempotencia (pago simple; para split generamos claves derivadas más abajo)
    if idempotency_key and not auto_split_propina:
        existing = Pago.objects.filter(
            venta=venta, idempotency_key=idempotency_key).first()
        if existing:
            _post_recalculo_y_pagado(venta)
            return [existing]

    # Asegurar saldo actualizado antes de decidir
    recalcular_saldo(venta)
    saldo = venta.saldo_pendiente or Decimal("0.00")

    # 1) Pago marcado explícitamente como propina → no descuenta saldo
    if es_propina:
        pago = Pago.objects.create(
            venta=venta,
            medio=medio,
            monto=monto,
            es_propina=True,
            referencia=referencia,
            notas=notas,
            idempotency_key=idempotency_key,
            creado_por=creado_por,
        )
        _post_recalculo_y_pagado(venta)
        return [pago]

    # 2) No propina y monto <= saldo
    if monto <= saldo:
        pago = Pago.objects.create(
            venta=venta,
            medio=medio,
            monto=monto,
            es_propina=False,
            referencia=referencia,
            notas=notas,
            idempotency_key=idempotency_key,
            creado_por=creado_por,
        )
        _post_recalculo_y_pagado(venta)
        return [pago]

    # 3) No propina y monto > saldo → confirmación o split
    diferencia = monto - saldo
    if not auto_split_propina:
        # La vista debe mostrar confirmación y reenviar con auto_split_propina=True si el usuario acepta
        raise OverpayNeedsConfirmation(saldo=saldo, monto=monto)

    # Split automático: saldo (no propina) + diferencia (propina)
    pagos: List[Pago] = []

    key_saldo = f"{idempotency_key}:saldo" if idempotency_key else None
    key_prop = f"{idempotency_key}:propina" if idempotency_key else None

    # Pago por el saldo (no propina)
    pago_saldo = None
    if key_saldo:
        pago_saldo = Pago.objects.filter(
            venta=venta, idempotency_key=key_saldo).first()
    if not pago_saldo:
        pago_saldo = Pago.objects.create(
            venta=venta,
            medio=medio,
            monto=saldo,
            es_propina=False,
            referencia=referencia,
            notas=notas,
            idempotency_key=key_saldo,
            creado_por=creado_por,
        )
    pagos.append(pago_saldo)

    # Pago por la diferencia como propina
    pago_prop = None
    if key_prop:
        pago_prop = Pago.objects.filter(
            venta=venta, idempotency_key=key_prop).first()
    if not pago_prop:
        pago_prop = Pago.objects.create(
            venta=venta,
            medio=medio,
            monto=diferencia,
            es_propina=True,
            referencia=referencia,
            notas=notas,
            idempotency_key=key_prop,
            creado_por=creado_por,
        )
    pagos.append(pago_prop)

    _post_recalculo_y_pagado(venta)
    return pagos


def _post_recalculo_y_pagado(venta) -> None:
    """
    Recalcula saldo y, si queda en 0, marca la venta como 'pagado' (según FSM permite).
    """
    recalcular_saldo(venta)
    if venta.saldo_pendiente == 0 and venta.estado != "pagado":
        # Esto soporta el circuito: se puede pasar a 'pagado' desde borrador/en_proceso.
        sales_services.marcar_pagada(venta=venta)


@transaction.atomic
def recalcular_saldo(venta) -> None:
    """
    Recalcula el saldo pendiente en base a pagos NO propina y persiste en la Venta.
    No toca la máquina de estados (eso lo hace _post_recalculo_y_pagado).
    """
    D = Decimal
    total_no_propina = (
        Pago.objects
        .filter(venta_id=venta.id, es_propina=False)
        .aggregate(total=models.Sum("monto"))["total"]
        or D("0.00")
    )
    nuevo_saldo = (venta.total or D("0.00")) - total_no_propina
    if nuevo_saldo < 0:
        nuevo_saldo = D("0.00")

    type(venta).objects.filter(pk=venta.pk).update(saldo_pendiente=nuevo_saldo)
    venta.saldo_pendiente = nuevo_saldo
