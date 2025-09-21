# apps/cashbox/selectors.py
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from django.db.models import Q, Prefetch
from django.utils import timezone

from apps.cashbox.models import CierreCaja, CierreCajaTotal


# -----------------------
# Selectores de lectura
# -----------------------

def cierres_por_fecha(
    *,
    empresa,
    sucursal=None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    abiertos: Optional[bool] = None,
):
    """
    Lista cierres de caja para una empresa (y sucursal opcional) filtrando por rango de fechas.

    - `desde`/`hasta` aplican sobre `abierto_en` (fecha de apertura del cierre).
    - `abiertos`:
        True  -> solo cierres con `cerrado_en IS NULL`
        False -> solo cierres con `cerrado_en IS NOT NULL`
        None  -> todos

    Retorna un QuerySet ordenado por `-abierto_en`.
    """
    qs = (
        CierreCaja.objects.select_related(
            "empresa", "sucursal", "usuario", "cerrado_por")
        .filter(empresa=empresa)
        .order_by("-abierto_en", "-creado_en")
    )

    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)

    if desde is not None:
        qs = qs.filter(abierto_en__gte=desde)
    if hasta is not None:
        qs = qs.filter(abierto_en__lte=hasta)

    if abiertos is True:
        qs = qs.filter(cerrado_en__isnull=True)
    elif abiertos is False:
        qs = qs.filter(cerrado_en__isnull=False)

    return qs


def get_cierre_abierto(*, empresa, sucursal) -> Optional[CierreCaja]:
    """
    Devuelve el **único** cierre abierto para la sucursal (o None si no hay).
    """
    return (
        CierreCaja.objects.select_related("empresa", "sucursal", "usuario")
        .filter(empresa=empresa, sucursal=sucursal, cerrado_en__isnull=True)
        .first()
    )


def detalle_con_totales(*, empresa, cierre_id) -> CierreCaja:
    """
    Carga un cierre por `id` validando tenant y prefetch de totales.
    """
    return (
        CierreCaja.objects.select_related(
            "empresa", "sucursal", "usuario", "cerrado_por")
        .prefetch_related(
            Prefetch(
                "totales",
                queryset=CierreCajaTotal.objects.select_related(
                    "medio").order_by("medio__nombre"),
            )
        )
        .get(empresa=empresa, id=cierre_id)
    )


def totales_de_cierre(*, cierre: CierreCaja):
    """
    Devuelve los totales del cierre (con `medio` ya seleccionado), ordenados por nombre del medio.
    """
    return cierre.totales.select_related("medio").order_by("medio__nombre")
