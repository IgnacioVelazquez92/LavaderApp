# apps/sales/services/items.py
"""
Comandos sobre VentaItem: agregar, actualizar cantidad, quitar.
Resuelven el precio vigente, recalculan totales y sincronizan estado de pago.
"""

from __future__ import annotations

from django.db import transaction
from django.core.exceptions import ValidationError

from apps.sales.models import Venta, VentaItem
from apps.sales.services.sales import (
    recalcular_totales,
    sync_payment_status_desde_saldo,
)
from apps.pricing.services.resolver import get_precio_vigente


def _assert_editable(venta: Venta) -> None:
    """
    Solo se permiten cambios a ítems en 'borrador' o 'en_proceso'.
    """
    if venta.estado not in ("borrador", "en_proceso"):
        raise ValidationError("No se pueden modificar ítems en este estado.")


@transaction.atomic
def _post_items_mutation_sync(venta: Venta) -> None:
    """
    Después de cambiar los ítems:
      - recalcula totales (incluye descuentos aplicados por ítem/venta)
      - recalcula saldo con pagos
      - sincroniza payment_status
    """
    # 1) Totales por ítems + ajustes (calculations usa venta.adjustments)
    recalcular_totales(venta=venta)

    # 2) Saldo con pagos actuales
    from apps.payments.services.payments import recalcular_saldo as _recalc_saldo
    _recalc_saldo(venta)

    # 3) payment_status (no_pagada/parcial/pagada)
    sync_payment_status_desde_saldo(venta=venta)


@transaction.atomic
def agregar_item(*, venta: Venta, servicio) -> VentaItem:
    """
    Agrega un ítem (una sola unidad) del servicio.
    - Sin cantidades: si ya existe, no duplica (mantiene el existente).
    - Cachea precio_unitario desde resolver.
    """
    _assert_editable(venta)

    try:
        precio = get_precio_vigente(
            empresa=venta.empresa,
            sucursal=venta.sucursal,
            servicio=servicio,
            tipo_vehiculo=venta.vehiculo.tipo,  # param correcto del resolver
        )
    except Exception:
        raise ValidationError(
            "No hay precio vigente para este servicio con el tipo de vehículo y sucursal seleccionados."
        )

    item, created = VentaItem.objects.get_or_create(
        venta=venta,
        servicio=servicio,
        defaults={"cantidad": 1, "precio_unitario": precio.precio},
    )
    # Si ya existía, mantenemos su cantidad y precio cacheado (MVP).

    _post_items_mutation_sync(venta)
    return item


@transaction.atomic
def agregar_items_batch(*, venta: Venta, servicios_ids: list[int]) -> list[str]:
    """
    Agrega múltiples servicios (uno cada uno), ignorando duplicados.
    Devuelve lista de mensajes de error (si los hubiera).
    """
    _assert_editable(venta)

    from apps.catalog.models import Servicio

    servicios = Servicio.objects.filter(
        empresa=venta.empresa, id__in=servicios_ids, activo=True
    )
    errores: list[str] = []

    for srv in servicios:
        try:
            agregar_item(venta=venta, servicio=srv)
        except ValidationError as e:
            errores.append(str(e))

    # Sincronización final (por si no hubo items nuevos pero sí hubo intentos)
    _post_items_mutation_sync(venta)
    return errores


@transaction.atomic
def actualizar_cantidad(*, item: VentaItem, cantidad: int) -> VentaItem:
    """
    Actualiza la cantidad de un ítem (>=1).
    Mantiene los ajustes por ítem (si existieran):
      - % se recalcula naturalmente sobre el nuevo subtotal del ítem
      - monto fijo queda como valor absoluto a restar
    """
    venta = item.venta
    _assert_editable(venta)

    if not isinstance(cantidad, int) or cantidad < 1:
        raise ValidationError(
            "La cantidad debe ser un entero mayor o igual a 1.")

    if item.cantidad == cantidad:
        # Nada cambia; devolvemos el mismo item
        return item

    item.cantidad = cantidad
    item.save(update_fields=["cantidad", "actualizado"])

    _post_items_mutation_sync(venta)
    return item


@transaction.atomic
def quitar_item(*, item: VentaItem) -> None:
    """
    Elimina un ítem de la venta.
    Los ajustes (SalesAdjustment) con FK al ítem se eliminan por CASCADE.
    """
    venta = item.venta
    _assert_editable(venta)

    item.delete()  # CASCADE borra descuentos por ítem
    _post_items_mutation_sync(venta)
