from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from django.db.models import QuerySet

from apps.invoicing.models import Comprobante


def por_venta(venta_id) -> Optional[Comprobante]:
    return (
        Comprobante.objects
        .select_related("empresa", "sucursal", "cliente", "cliente_facturacion", "venta")
        .filter(venta_id=venta_id)
        .first()
    )


def por_rango(*, empresa=None, sucursal=None, tipo=None, desde: date = None, hasta: date = None) -> QuerySet[Comprobante]:
    qs = (
        Comprobante.objects
        .select_related("empresa", "sucursal", "cliente", "cliente_facturacion", "venta")
        .all()
    )
    if empresa:
        qs = qs.filter(empresa=empresa)
    if sucursal:
        qs = qs.filter(sucursal=sucursal)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if desde:
        qs = qs.filter(emitido_en__date__gte=desde)
    if hasta:
        qs = qs.filter(emitido_en__date__lte=hasta)
    return qs.order_by("-emitido_en")
