# apps/sales/services/sales.py
"""
Comandos principales sobre el modelo Venta.
Capa de mutaciones: no renderiza, no maneja requests.
"""

from __future__ import annotations

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.sales.calculations import calcular_totales
from apps.sales.fsm import VentaEstado, puede_transicionar
from apps.sales.models import Venta


# ---------------------------------------------------------------------
# Helpers de PAGO (payment_status)
# ---------------------------------------------------------------------

def _resolver_payment_status_desde_saldo(*, venta: Venta) -> str:
    """
    Devuelve el payment_status esperado según total y saldo_pendiente.
      - saldo == total -> no_pagada
      - 0 < saldo < total -> parcial
      - saldo == 0 -> pagada
    """
    total = (venta.total or Decimal("0"))
    saldo = (venta.saldo_pendiente or Decimal("0"))

    if saldo <= Decimal("0"):
        return "pagada"
    if saldo >= total:
        return "no_pagada"
    return "parcial"


@transaction.atomic
def sync_payment_status_desde_saldo(*, venta: Venta, actor=None) -> Venta:
    """
    Sincroniza payment_status en base a 'total' y 'saldo_pendiente' actuales.
    Dispara hook 'on_pagada' si cambia a 'pagada'.
    """
    nuevo = _resolver_payment_status_desde_saldo(venta=venta)
    if nuevo != venta.payment_status:
        prev = venta.payment_status
        venta.payment_status = nuevo
        venta.save(update_fields=["payment_status", "actualizado"])

        # Hook si pasó a 'pagada'
        if nuevo == "pagada":
            from apps.sales.services import lifecycle as lifecycle_services
            try:
                lifecycle_services.on_pagada(
                    venta, prev_payment_status=prev, actor=actor)
            except Exception:
                pass
    return venta


@transaction.atomic
def set_payment_status(*, venta: Venta, payment_status: str, actor=None) -> Venta:
    """
    Cambia payment_status explícitamente (casos excepcionales).
    Dispara hook si cambia a 'pagada'.
    """
    if payment_status not in {"no_pagada", "parcial", "pagada"}:
        raise ValidationError("payment_status inválido.")

    prev = venta.payment_status
    if prev == payment_status:
        return venta

    venta.payment_status = payment_status
    venta.save(update_fields=["payment_status", "actualizado"])

    if payment_status == "pagada":
        from apps.sales.services import lifecycle as lifecycle_services
        try:
            lifecycle_services.on_pagada(
                venta, prev_payment_status=prev, actor=actor)
        except Exception:
            pass

    return venta


# ---------------------------------------------------------------------
# CRUD / Totales
# ---------------------------------------------------------------------

@transaction.atomic
def crear_venta(*, empresa, sucursal, cliente, vehiculo, creado_por, notas: str = "") -> Venta:
    """
    Crea una nueva Venta en estado 'borrador'.
    payment_status inicia en 'no_pagada'.
    """
    venta = Venta.objects.create(
        empresa=empresa,
        sucursal=sucursal,
        cliente=cliente,
        vehiculo=vehiculo,
        estado=VentaEstado.BORRADOR,
        notas=notas,
        creado_por=creado_por,
        # payment_status usa el default del modelo: "no_pagada"
    )
    return venta


@transaction.atomic
def actualizar_venta(*, venta: Venta, notas: str | None = None) -> Venta:
    """
    Actualiza campos simples de la venta (ej. notas).
    """
    if notas is not None:
        venta.notas = notas
    venta.save(update_fields=["notas", "actualizado"])
    return venta


@transaction.atomic
def recalcular_totales(*, venta: Venta) -> Venta:
    """
    Recalcula todos los totales de una venta a partir de sus ítems y ajustes.
    (Subtotal, propina, descuento, total. El saldo_pendiente depende de pagos.)

    Nota:
    - `calculations.calcular_totales` devuelve `saldo_pendiente = total` como baseline.
      La capa de payments luego debe recalcularlo en base a pagos reales.
    """
    items_qs = venta.items.all()
    # Pasamos los ajustes (descuentos) para soportar item/order, %/monto:
    adjustments_qs = venta.adjustments.select_related("item").all()

    data = calcular_totales(
        items=items_qs,
        descuento=venta.descuento,       # legacy; será ignorado si adjustments no está vacío
        propina=venta.propina or Decimal("0.00"),
        adjustments=adjustments_qs,
    )
    for field, value in data.items():
        setattr(venta, field, value)
    venta.save(update_fields=list(data.keys()) + ["actualizado"])
    return venta


# ---------------------------------------------------------------------
# FSM del PROCESO (estado)
# ---------------------------------------------------------------------

@transaction.atomic
def cambiar_estado(*, venta: Venta, nuevo_estado: str) -> Venta:
    """
    Transición de estado con validación FSM (proceso).
    """
    if not puede_transicionar(venta.estado, nuevo_estado):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a {nuevo_estado}")
    prev = venta.estado
    venta.estado = nuevo_estado
    venta.save(update_fields=["estado", "actualizado"])

    # Hooks de proceso según el destino
    from apps.sales.services import lifecycle as lifecycle_services
    try:
        if nuevo_estado == VentaEstado.EN_PROCESO:
            lifecycle_services.on_iniciar(venta, prev_estado=prev)
        elif nuevo_estado == VentaEstado.TERMINADO:
            lifecycle_services.on_finalizar(venta, prev_estado=prev)
        elif nuevo_estado == VentaEstado.CANCELADO:
            lifecycle_services.on_cancelar(venta, prev_estado=prev)
    except Exception:
        pass

    return venta


@transaction.atomic
def iniciar_trabajo(*, venta: Venta, actor=None) -> Venta:
    """
    Marca la venta como 'en_proceso'.
    - No depende del pago.
    - Respeta FSM (borrador -> en_proceso).
    - Rechaza si está cancelada.
    """
    if venta.estado == VentaEstado.CANCELADO:
        raise ValidationError("La venta está cancelada.")

    if not puede_transicionar(venta.estado, VentaEstado.EN_PROCESO):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a en_proceso")

    prev = venta.estado
    venta.estado = VentaEstado.EN_PROCESO
    venta.save(update_fields=["estado", "actualizado"])

    from apps.sales.services import lifecycle as lifecycle_services  # import local
    try:
        lifecycle_services.on_iniciar(venta, prev_estado=prev, actor=actor)
    except Exception:
        pass

    return venta


@transaction.atomic
def finalizar_trabajo(*, venta: Venta, actor=None) -> Venta:
    """
    Marca la venta como 'terminado' (cierre operativo).
    NO toca pagos ni saldo.
    Está permitido venir desde 'borrador' o 'en_proceso' (según FSM).
    """
    if venta.estado == VentaEstado.CANCELADO:
        raise ValidationError("La venta está cancelada.")

    if not puede_transicionar(venta.estado, VentaEstado.TERMINADO):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a terminado")

    prev = venta.estado
    venta.estado = VentaEstado.TERMINADO
    venta.save(update_fields=["estado", "actualizado"])

    from apps.sales.services import lifecycle as lifecycle_services  # import local
    try:
        lifecycle_services.on_finalizar(venta, prev_estado=prev, actor=actor)
    except Exception:
        pass

    return venta


@transaction.atomic
def finalizar_venta(*, venta: Venta, actor=None) -> Venta:
    """
    Acción compuesta (convenience):
      - Recalcula totales (incluye descuentos).
      - Recalcula saldo vía payments.
      - Sincroniza payment_status desde saldo.
      - Pasa a 'terminado' (si la FSM lo permite).

    Nota: no fuerza 'pagada'; eso lo decide sync_payment_status (saldo==0).
    """
    # 1) Totales por ítems + ajustes
    recalcular_totales(venta=venta)

    # 2) Recalcular saldo con pagos (estado del dinero)
    from apps.payments.services.payments import recalcular_saldo as _recalc_saldo  # import local
    _recalc_saldo(venta)

    # 3) Sincronizar payment_status
    sync_payment_status_desde_saldo(venta=venta, actor=actor)

    # 4) Pasar a TERMINADO (si corresponde)
    if puede_transicionar(venta.estado, VentaEstado.TERMINADO):
        prev = venta.estado
        venta.estado = VentaEstado.TERMINADO
        venta.save(update_fields=["estado", "actualizado"])
        from apps.sales.services import lifecycle as lifecycle_services
        try:
            lifecycle_services.on_finalizar(
                venta, prev_estado=prev, actor=actor)
        except Exception:
            pass

    return venta


@transaction.atomic
def cancelar_venta(*, venta: Venta) -> Venta:
    """
    Marca la venta como cancelada.

    Política por defecto:
    - Bloquea cancelar si hay pagos (payment_status != 'no_pagada').
      (Para permitirlo, habría que implementar reversos/nota de crédito primero.)
    """
    if venta.payment_status != "no_pagada":
        raise ValidationError(
            "No se puede cancelar una venta con pagos registrados.")

    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.CANCELADO)


# ---------------------------------------------------------------------
# Casos excepcionales
# ---------------------------------------------------------------------

@transaction.atomic
def marcar_pagada(*, venta: Venta, actor=None) -> Venta:
    """
    Marca la venta como 'pagada' a nivel payment_status.
    NO cambia el estado operativo del proceso.
    """
    return set_payment_status(venta=venta, payment_status="pagada", actor=actor)
