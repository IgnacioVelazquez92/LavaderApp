# apps/reports/selectors/sales_selectors.py
from __future__ import annotations

from typing import Iterable, Optional

from django.db.models import F
from django.db.models.functions import TruncDate, ExtractMonth, ExtractYear

from apps.reports.selectors.base import (
    DateRange,
    apply_date_range,
    apply_sucursal,
    apply_sales_statuses,
    count_,
    filter_by_empresa,
    sum_,
    avg_,
)

from apps.sales.models import Venta
from django.db.models import F, OuterRef, Subquery, IntegerField, Value, Sum as DjSum
from django.db.models.functions import TruncDate, ExtractMonth, ExtractYear, Coalesce as DjCoalesce
from apps.sales.models import Venta, VentaItem
from apps.reports.selectors.base import (
    DateRange, apply_date_range, apply_sucursal, apply_sales_statuses,
    count_, filter_by_empresa, sum_, avg_,
)

# ============================================================
# SELECTORS — Reportes basados en ventas
# ============================================================


def ventas_por_dia(*, empresa, sucursal=None, dr: DateRange, estados=None):
    """
    Serie diaria de ventas sin fan-out por items.
    Devuelve: fecha, ventas, total_monto, total_items, ticket_promedio.
    """
    # Subquery: cantidad total de ítems por venta (evita JOIN en el QS principal)
    items_por_venta = (
        VentaItem.objects
        .filter(venta=OuterRef("pk"))
        .values("venta")
        .annotate(cnt=DjSum("cantidad"))
        .values("cnt")[:1]
    )

    qs = Venta.objects.all().select_related("sucursal")
    qs = filter_by_empresa(qs, empresa=empresa)
    qs = apply_sucursal(qs, sucursal=sucursal)
    qs = apply_date_range(qs, field="creado", dr=dr, field_is_date=False)
    if estados:
        qs = apply_sales_statuses(qs, estados=estados, field="estado")

    # Anotar por venta, sin joinear items
    qs = qs.annotate(
        fecha=TruncDate("creado"),
        items_count=DjCoalesce(Subquery(items_por_venta, output_field=IntegerField(
        )), Value(0), output_field=IntegerField()),
    )

    # Agregar por día, ahora sin duplicación
    return (
        qs.values("fecha")
          .annotate(
              ventas=count_(),  # correcto (cuenta ventas reales)
              total_monto=sum_("total"),
              total_items=DjCoalesce(DjSum("items_count", output_field=IntegerField()), Value(
                  0), output_field=IntegerField()),
              ticket_promedio=avg_("total"),
        )
        .order_by("fecha")
    )


def ventas_por_turno(*, empresa, sucursal=None, dr: DateRange):
    """
    Ventas agrupadas por turno de caja.
    Claves: turno_id, sucursal__nombre, abierto_en, cerrado_en, ventas, total_ventas.
    """
    qs = Venta.objects.all().select_related("sucursal", "turno")
    qs = filter_by_empresa(qs, empresa=empresa)
    qs = apply_sucursal(qs, sucursal=sucursal)
    qs = apply_date_range(qs, field="creado", dr=dr, field_is_date=False)

    return (
        qs.values("turno_id", "sucursal__nombre")
        .annotate(
            abierto_en=F("turno__abierto_en"),
            cerrado_en=F("turno__cerrado_en"),
            ventas=count_(),
            total_ventas=sum_("total"),
        )
        .order_by("abierto_en", "turno_id")
    )


def ventas_mensual_por_sucursal(*, empresa, dr: DateRange):
    """
    Consolidado mensual por sucursal.
    Claves: anio, mes, sucursal__nombre, ventas, total_ventas, ticket_promedio.
    """
    qs = Venta.objects.all().select_related("sucursal")
    qs = filter_by_empresa(qs, empresa=empresa)
    qs = apply_date_range(qs, field="creado", dr=dr, field_is_date=False)

    return (
        qs.values("sucursal__nombre")
        .annotate(
            anio=ExtractYear("creado"),
            mes=ExtractMonth("creado"),
            ventas=count_(),
            total_ventas=sum_("total"),
            ticket_promedio=avg_("total"),
        )
        .order_by("anio", "mes", "sucursal__nombre")
    )
