# apps/reports/selectors/base.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeVar
from django.db.models import DecimalField, IntegerField, FloatField
from django.db.models import Q, QuerySet, Sum, Count, Avg, F, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone


# =============================================================================
# Propósito de este módulo
# -----------------------------------------------------------------------------
# Proveer utilidades COMUNES para todos los selectors de reportería:
#   - Normalizar filtros de tenencia (empresa/sucursal) y contexto (turno).
#   - Armar filtros de rango de FECHAS con seguridad (date vs datetime).
#   - Helpers de agregación "a prueba de NULL" (Coalesce).
#   - Shortcuts para filtrar por estados de venta o métodos de pago.
# =============================================================================


@dataclass(frozen=True)
class DateRange:
    """
    Rango de fechas CERRADO [desde, hasta], expresado con objetos 'date' (sin tiempo).
    """
    desde: date
    hasta: date

    def ensure_order(self) -> "DateRange":
        """Retorna un nuevo DateRange con orden corregido si fuese necesario."""
        if self.desde <= self.hasta:
            return self
        return DateRange(desde=self.hasta, hasta=self.desde)

    def as_tuple(self) -> Tuple[date, date]:
        """Devuelve el rango como tupla (desde, hasta)."""
        d = self.ensure_order()
        return (d.desde, d.hasta)


T = TypeVar("T", bound=QuerySet)


# =========================
# Tenancy
# =========================

def filter_by_empresa(qs: T, *, empresa: Any, field: str = "empresa") -> T:
    """Filtra por empresa (FK o UUID)."""
    if empresa is None:
        return qs
    return qs.filter(**{field: empresa})


def apply_sucursal(qs: T, *, sucursal: Optional[Any], field: str = "sucursal") -> T:
    """Filtra por sucursal si fue provista; si es None, no modifica el QS."""
    if sucursal is None:
        return qs
    return qs.filter(**{field: sucursal})


# =========================
# Rango de fechas
# =========================

def daterange_to_datetimes(dr: DateRange, tz: Optional[dt_timezone] = None) -> Tuple[datetime, datetime]:
    """
    Convierte un DateRange (dates) a límites datetime INCLUYENTES en la zona horaria dada.
      start = 00:00:00 del 'desde'
      end   = 23:59:59.999999 del 'hasta'
    """
    dr = dr.ensure_order()
    tzinfo = tz or timezone.get_current_timezone()
    start = datetime.combine(dr.desde, time.min).replace(tzinfo=tzinfo)
    end = (datetime.combine(dr.hasta, time.min).replace(
        tzinfo=tzinfo) + timedelta(days=1)) - timedelta(microseconds=1)
    return start, end


def range_kwargs_for(field: str, dr: DateRange, *, field_is_date: bool) -> Dict[str, Any]:
    """Arma kwargs __gte/__lte apropiados según el tipo de campo temporal."""
    if field_is_date:
        d1, d2 = dr.as_tuple()
        return {f"{field}__gte": d1, f"{field}__lte": d2}
    else:
        start_dt, end_dt = daterange_to_datetimes(dr)
        return {f"{field}__gte": start_dt, f"{field}__lte": end_dt}


def apply_date_range(
    qs: T,
    *,
    field: str,
    dr: DateRange,
    field_is_date: bool = False,
) -> T:
    """Aplica filtro de rango temporal interpretando correctamente el tipo del campo."""
    if dr is None:
        return qs
    return qs.filter(**range_kwargs_for(field, dr, field_is_date=field_is_date))


# =========================
# Turnos de caja
# =========================

def apply_turno(qs: T, *, turno: Optional[Any], field: str = "turno") -> T:
    """Filtra por turno operativo si se pasó; si es None, no aplica."""
    if turno is None:
        return qs
    return qs.filter(**{field: turno})


# =========================
# Métodos de pago / Estados de venta
# =========================

def apply_payment_methods(qs: T, *, metodo_ids: Optional[Iterable[int]], field: str = "medio_id") -> T:
    """Filtra por IDs de métodos de pago si se provee una lista/iterable."""
    if not metodo_ids:
        return qs
    ids = [int(x) for x in metodo_ids if str(x).strip() != ""]
    if not ids:
        return qs
    return qs.filter(**{f"{field}__in": ids})


def apply_sales_statuses(qs: T, *, estados: Optional[Iterable[str]], field: str = "estado") -> T:
    """Filtra por estados de venta si se provee una lista/iterable."""
    if not estados:
        return qs
    vals = [str(x) for x in estados if str(x).strip() != ""]
    if not vals:
        return qs
    return qs.filter(**{f"{field}__in": vals})


# =========================
# Agregaciones seguras (NULL→0)
# =========================


def sum_(expr: Any, default: int | float = 0):
    if isinstance(expr, str):
        expr = F(expr)
    return Coalesce(Sum(expr, output_field=DecimalField()), Value(default), output_field=DecimalField())


def count_(expr: Any = "id", distinct: bool = False, default: int = 0):
    if isinstance(expr, str):
        expr = F(expr)
    return Coalesce(Count(expr, distinct=distinct, output_field=IntegerField()), Value(default), output_field=IntegerField())


def avg_(expr: Any, default: float = 0.0):
    if isinstance(expr, str):
        expr = F(expr)
    return Coalesce(Avg(expr, output_field=DecimalField()), Value(default), output_field=DecimalField())

# =========================
# Shortcuts de proyección/orden
# =========================


def values_ordered(qs: T, values_fields: Iterable[str], order_by: Iterable[str]) -> List[Dict[str, Any]]:
    """Proyecta a dicts con .values(...) y ordena con .order_by(...)."""
    return list(qs.values(*values_fields).order_by(*order_by))
