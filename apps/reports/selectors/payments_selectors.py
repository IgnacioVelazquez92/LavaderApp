# apps/reports/selectors/payments_selectors.py
from __future__ import annotations

from typing import Iterable, Optional
from django.db.models import Sum, Value, DecimalField, Q, F
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from apps.reports.selectors.base import (
    DateRange,
    apply_date_range,
    apply_payment_methods,
    apply_sucursal,
)

from apps.payments.models import Pago


def pagos_por_metodo(
    *, empresa, sucursal=None, dr: DateRange, metodo_ids: Optional[Iterable[int]] = None
):
    """
    Totales de pagos por método, separando monto (sin propina) y propinas.
    Claves: medio__nombre, total, propinas
    """
    qs = Pago.objects.all().select_related("medio", "venta", "venta__sucursal")
    qs = qs.filter(venta__empresa=empresa)
    qs = apply_sucursal(qs, sucursal=sucursal, field="venta__sucursal")
    qs = apply_date_range(qs, field="creado_en", dr=dr, field_is_date=False)
    qs = apply_payment_methods(qs, metodo_ids=metodo_ids, field="medio_id")

    return (
        qs.values(metodo=F("medio__nombre"))   # <- alias consistente
        .annotate(
            total=Coalesce(
                Sum("monto", filter=Q(es_propina=False),
                    output_field=DecimalField()),
                Value(0, output_field=DecimalField()),
                output_field=DecimalField(),
            ),
            propinas=Coalesce(
                Sum("monto", filter=Q(es_propina=True),
                    output_field=DecimalField()),
                Value(0, output_field=DecimalField()),
                output_field=DecimalField(),
            ),
        )
        .order_by("metodo")                  # <- orden por alias
    )


def ingresos_mensuales_por_metodo(*, empresa, dr: DateRange):
    """
    Ingresos por método por mes (monto y propinas separados).
    Claves: anio, mes, medio__nombre, total, propinas
    """
    qs = Pago.objects.all().select_related("medio", "venta")
    qs = qs.filter(venta__empresa=empresa)
    qs = apply_date_range(qs, field="creado_en", dr=dr, field_is_date=False)

    return (
        qs.values(metodo=F("medio__nombre"))
        .annotate(
            anio=ExtractYear("creado_en"),
            mes=ExtractMonth("creado_en"),
            total=Coalesce(...),
            propinas=Coalesce(...),
        )
        .order_by("anio", "mes", "metodo")
    )


def propinas_por_usuario(*, empresa, dr: DateRange):
    """
    Propinas agrupadas por usuario creador del pago.
    Claves: creado_por__username, propinas
    """
    qs = Pago.objects.all().select_related("creado_por", "venta")
    qs = qs.filter(venta__empresa=empresa)
    qs = apply_date_range(qs, field="creado_en", dr=dr, field_is_date=False)

    return (
        qs.values("creado_por__username")
        .annotate(
            propinas=Coalesce(
                Sum("monto", filter=Q(es_propina=True),
                    output_field=DecimalField()),
                Value(0, output_field=DecimalField()),
                output_field=DecimalField(),
            )
        )
        .order_by("creado_por__username")
    )
