# apps/sales/services/items.py
"""
Comandos sobre VentaItem: agregar, actualizar cantidad, quitar.
Se encargan de resolver el precio vigente y recalcular totales.
"""

# apps/sales/services/items.py
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.sales.models import Venta, VentaItem
from apps.sales.services.sales import recalcular_totales
from apps.pricing.services.resolver import get_precio_vigente


@transaction.atomic
def agregar_item(*, venta: Venta, servicio) -> VentaItem:
    """
    Agrega un ítem (una sola unidad) del servicio.
    - Sin cantidades: si ya existe, no duplica.
    - Cachea precio_unitario desde resolver.
    """
    if venta.estado not in ["borrador", "en_proceso"]:
        raise ValidationError("No se pueden agregar ítems en este estado")

    try:
        precio = get_precio_vigente(
            empresa=venta.empresa,
            sucursal=venta.sucursal,
            servicio=servicio,
            tipo_vehiculo=venta.vehiculo.tipo,
        )
    except Exception:
        raise ValidationError(
            "No hay precio vigente para este servicio con el tipo de vehículo y sucursal seleccionados."
        )

    item, created = VentaItem.objects.get_or_create(
        venta=venta, servicio=servicio,
        defaults={"cantidad": 1, "precio_unitario": precio.precio},
    )
    # Si ya existía, no hacemos nada (no hay cantidades).
    recalcular_totales(venta=venta)
    return item


@transaction.atomic
def agregar_items_batch(*, venta: Venta, servicios_ids: list[int]):
    """
    Agrega múltiples servicios (uno cada uno), ignorando duplicados.
    """
    from apps.catalog.models import Servicio

    servicios = Servicio.objects.filter(
        empresa=venta.empresa, id__in=servicios_ids, activo=True
    )
    errores = []
    for srv in servicios:
        try:
            agregar_item(venta=venta, servicio=srv)
        except ValidationError as e:
            errores.append(str(e))

    recalcular_totales(venta=venta)
    return errores


@transaction.atomic
def quitar_item(*, item: VentaItem):
    """
    Elimina un ítem de la venta.
    """
    venta = item.venta
    if venta.estado not in ["borrador", "en_proceso"]:
        raise ValidationError("No se pueden eliminar ítems en este estado")

    item.delete()
    recalcular_totales(venta=venta)
