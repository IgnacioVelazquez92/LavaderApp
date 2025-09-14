# apps/payments/services/payments.py
from decimal import Decimal
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.payments.models import Pago, MedioPago
from apps.sales.services import sales as sales_services


@transaction.atomic
def registrar_pago(
    venta,
    medio: MedioPago,
    monto: Decimal,
    es_propina: bool,
    referencia: str | None,
    notas: str | None,
    creado_por,
    idempotency_key: str | None = None,
) -> Pago:
    """
    Registra un nuevo pago asociado a una venta.

    Validaciones:
    - monto > 0
    - medio.empresa == venta.empresa  (integridad tenant)
    - no sobrepago si es_propina=False
    - idempotencia por (venta, idempotency_key)
    """
    # monto > 0
    if monto is None or monto <= 0:
        raise ValidationError(_("El monto del pago debe ser mayor a 0."))

    # Tenant: el medio debe pertenecer a la misma empresa que la venta
    if medio.empresa_id != venta.empresa_id:
        raise ValidationError(
            _("El medio de pago no pertenece a la empresa de la venta."))

    # Idempotencia
    if idempotency_key:
        existing = Pago.objects.filter(
            venta=venta, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    # No permitir sobrepago si NO es propina
    if not es_propina and monto > venta.saldo_pendiente:
        raise ValidationError(
            _("El monto no puede exceder el saldo pendiente de la venta."))

    # Crear pago
    pago = Pago.objects.create(
        venta=venta,
        medio=medio,
        monto=monto,
        es_propina=es_propina,
        referencia=referencia,
        notas=notas,
        idempotency_key=idempotency_key,
        creado_por=creado_por,
    )

    # Recalcular saldo y actualizar estado de la venta
    recalcular_saldo(venta)

    return pago


def recalcular_saldo(venta) -> None:
    """
    Recalcula el saldo pendiente en base a los pagos (excluyendo propinas).
    Si queda en 0, marca la venta como 'pagado'.
    """
    # Total abonado (sin propinas)
    total_abonado = (
        venta.pagos.filter(es_propina=False)
        .aggregate(total=models.Sum("monto"))["total"]
        or Decimal("0.00")
    )

    nuevo_saldo = venta.total - total_abonado
    if nuevo_saldo < 0:
        nuevo_saldo = Decimal("0.00")

    venta.saldo_pendiente = nuevo_saldo
    venta.save(update_fields=["saldo_pendiente"])

    if venta.saldo_pendiente == 0 and venta.estado != "pagado":
        sales_services.marcar_pagado(venta)
