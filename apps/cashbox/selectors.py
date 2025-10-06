# apps/cashbox/selectors.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.db.models import Prefetch
from apps.cashbox.models import TurnoCaja, TurnoCajaTotal


# -----------------------
# Selectores de lectura (Turnos)
# -----------------------

def turnos_por_fecha(
    *,
    empresa,
    sucursal=None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    abiertos: Optional[bool] = None,
):
    """
    Lista turnos de caja para una empresa (y sucursal opcional) filtrando por rango de fechas.

    - `desde`/`hasta` aplican sobre `abierto_en` (fecha de apertura del turno).
    - `abiertos`:
        True  -> solo turnos con `cerrado_en IS NULL`
        False -> solo turnos con `cerrado_en IS NOT NULL`
        None  -> todos

    Retorna un QuerySet ordenado por `-abierto_en`.
    """
    qs = (
        TurnoCaja.objects.select_related(
            "empresa", "sucursal", "abierto_por", "cerrado_por")
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


def get_turno_abierto(*, empresa, sucursal) -> Optional[TurnoCaja]:
    """
    Devuelve el turno abierto (si existe) para la sucursal.
    """
    return (
        TurnoCaja.objects.select_related("empresa", "sucursal", "abierto_por")
        .filter(empresa=empresa, sucursal=sucursal, cerrado_en__isnull=True)
        .order_by("-abierto_en")
        .first()
    )


def detalle_con_totales(*, empresa, turno_id) -> TurnoCaja:
    """
    Carga un turno por `id` validando tenant y prefetch de totales.
    """
    return (
        TurnoCaja.objects.select_related(
            "empresa", "sucursal", "abierto_por", "cerrado_por")
        .prefetch_related(
            Prefetch(
                "totales",
                queryset=TurnoCajaTotal.objects.order_by("medio"),
            )
        )
        .get(empresa=empresa, id=turno_id)
    )


def totales_de_turno(*, turno: TurnoCaja):
    """
    Devuelve los totales del turno ordenados por nombre del medio.
    """
    return turno.totales.order_by("medio")
