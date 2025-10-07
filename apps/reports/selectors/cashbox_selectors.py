# apps/reports/selectors/cashbox_selectors.py
from __future__ import annotations

from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from apps.reports.selectors.base import (
    DateRange,
    apply_date_range,
    apply_sucursal,
    filter_by_empresa,
)

# Usamos Venta para calcular totales por turno
from apps.sales.models import Venta


# ============================================================
# SELECTORS — Reportes de Caja (Cashbox)
# ============================================================

def totales_por_turno(*, empresa, sucursal=None, dr: DateRange):
    """
    Suma de ventas por turno (sin discriminar método de pago).
    Claves: turno_id, sucursal__nombre, abierto_en, cerrado_en, total_ventas, ventas.
    """
    qs = Venta.objects.all().select_related("turno", "sucursal")
    qs = filter_by_empresa(qs, empresa=empresa)
    qs = apply_sucursal(qs, sucursal=sucursal)
    # Campo temporal real: Venta.creado (DateTime)
    qs = apply_date_range(qs, field="creado", dr=dr, field_is_date=False)

    return (
        qs.values("turno_id", "sucursal__nombre")
        .annotate(
            abierto_en=F("turno__abierto_en"),
            cerrado_en=F("turno__cerrado_en"),
            ventas=Coalesce(Sum(Value(1)), 0),
            total_ventas=Coalesce(Sum("total"), Value(0.0)),
        )
        .order_by("abierto_en", "turno_id")
    )


def cierres_por_dia(*, empresa, sucursal=None, dr: DateRange):
    """
    Consolidado diario de ventas (base para el Cierre Z).
    Claves: fecha, sucursal__nombre, total_teorico (suma total ventas del día).
    """
    qs = Venta.objects.all().select_related("sucursal")
    qs = filter_by_empresa(qs, empresa=empresa)
    qs = apply_sucursal(qs, sucursal=sucursal)
    qs = apply_date_range(qs, field="creado", dr=dr, field_is_date=False)

    return (
        qs.annotate(fecha=TruncDate("creado"))
        .values("fecha", "sucursal__nombre")
        .annotate(total_teorico=Coalesce(Sum("total"), Value(0.0)))
        .order_by("fecha", "sucursal__nombre")
    )
