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


@transaction.atomic
def crear_venta(*, empresa, sucursal, cliente, vehiculo, creado_por, notas: str = "") -> Venta:
    """
    Crea una nueva Venta en estado 'borrador'.
    """
    venta = Venta.objects.create(
        empresa=empresa,
        sucursal=sucursal,
        cliente=cliente,
        vehiculo=vehiculo,
        estado=VentaEstado.BORRADOR,
        notas=notas,
        creado_por=creado_por,
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
    Recalcula todos los totales de una venta a partir de sus ítems.
    (Subtotal, propina, descuento, total. El saldo_pendiente depende de pagos.)
    """
    data = calcular_totales(venta.items.all(), venta.descuento, venta.propina)
    for field, value in data.items():
        setattr(venta, field, value)
    venta.save(update_fields=list(data.keys()) + ["actualizado"])
    return venta


@transaction.atomic
def cambiar_estado(*, venta: Venta, nuevo_estado: str) -> Venta:
    """
    Transición de estado con validación FSM.
    """
    if not puede_transicionar(venta.estado, nuevo_estado):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a {nuevo_estado}")
    venta.estado = nuevo_estado
    venta.save(update_fields=["estado", "actualizado"])
    return venta


@transaction.atomic
def finalizar_venta(*, venta: Venta, actor=None) -> Venta:
    """
    Cierra la edición de la venta. Según saldo:
      - Si saldo_pendiente > 0  -> deja la venta en 'terminado'
      - Si saldo_pendiente == 0 -> 'terminado' y luego 'pagado' (en la misma transacción)

    Notas:
    - Primero recalculamos totales e IMPORTANTE: sincronizamos saldo con pagos
      para decidir con datos frescos.
    - Respetamos la FSM: si para llegar a 'pagado' hace falta pasar por 'terminado',
      se hacen ambas transiciones en orden.
    """
    # 1) Totales por ítems (seguridad)
    recalcular_totales(venta=venta)

    # 2) Sincronizar saldo con pagos (evita depender de saldo viejo)
    #    Import local para evitar dependencia circular a módulo-level.
    from apps.payments.services.payments import recalcular_saldo as _recalc_saldo
    _recalc_saldo(venta)

    # 3) Pasar a TERMINADO (bloquea edición) — deja que la FSM valide
    cambiar_estado(venta=venta, nuevo_estado=VentaEstado.TERMINADO)

    # 4) Si el saldo quedó en 0, pasar a PAGADO
    if (venta.saldo_pendiente or Decimal("0.00")) == Decimal("0.00"):
        cambiar_estado(venta=venta, nuevo_estado=VentaEstado.PAGADO)

    return venta


@transaction.atomic
def cancelar_venta(*, venta: Venta) -> Venta:
    """Marca la venta como cancelada."""
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.CANCELADO)


@transaction.atomic
def marcar_pagada(*, venta: Venta) -> Venta:
    """
    Marca la venta como pagada.
    Uso excepcional (p. ej. tareas de conciliación). En el circuito estándar,
    NO LLAMAR desde payments: la decisión se toma en `finalizar_venta()`.
    """
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.PAGADO)


@transaction.atomic
def finalizar_trabajo(*, venta, actor=None):
    """
    Marca la venta como 'terminado' (cierre operativo).
    NO toca pagos ni saldo.
    Está permitido venir desde 'borrador', 'en_proceso' o 'pagado'.
    """
    if not puede_transicionar(venta.estado, VentaEstado.TERMINADO):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a terminado")

    venta.estado = VentaEstado.TERMINADO
    venta.save(update_fields=["estado", "actualizado"])

    # Hook de notificación, etc.
    from apps.sales.services import lifecycle as lifecycle_services
    lifecycle_services.on_finalizar(venta, actor=actor)
    return venta
