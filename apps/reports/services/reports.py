# apps/reports/services/reports.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, TypedDict

from django.utils.translation import gettext_lazy as _

# Selectors de lectura (solo agregaciones). Cada archivo implementa consultas
# específicas sobre sus módulos, aplicando tenancy y filtros.
from apps.reports.selectors.base import (
    DateRange,
    apply_date_range,
    apply_payment_methods,
    apply_sales_statuses,
    apply_sucursal,
    apply_turno,
    filter_by_empresa,
    values_ordered,
)
from apps.reports import models as m_reports

# Selectors concretos (a implementar en archivos vecinos).
# Las funciones invocadas en este service están documentadas abajo.
from ..selectors import sales_selectors as sales_sel   # OK
from ..selectors import payments_selectors as pay_sel  # OK
from ..selectors import cashbox_selectors as cbx_sel   # OK


# =============================================================================
# Propósito del módulo
# -----------------------------------------------------------------------------
# Orquestar la construcción de resultados de REPORTES utilizando EXCLUSIVAMENTE
# agregaciones provistas por los selectors. Aquí NO se recalculan totales
# de negocio (ventas/pagos/caja); solo se consolidan y normalizan datos ya
# calculados por los módulos fuentes.
#
# Principios:
# - Funciones puras que reciben empresa + params y devuelven DTOs listos para UI/export.
# - Toda la validación de formularios y el contrato de 'params' lo hace forms/filters.py.
# - Este módulo NO accede a request ni a la sesión. Se le inyecta la empresa/filtros.
# - Los nombres de las keys devueltas se estabilizan aquí (contrato con templates/export).
# =============================================================================


# =========================
# Tipos / DTOs
# =========================

class SerieDia(TypedDict):
    fecha: date
    ventas: int
    total_monto: float
    total_items: int
    ticket_promedio: float


class MetodoResumen(TypedDict):
    metodo: str
    total: float
    propinas: float


class TurnoResumen(TypedDict):
    turno_id: int
    sucursal: str
    abierto_en: str
    cerrado_en: Optional[str]
    ventas: int
    total_ventas: float


@dataclass(frozen=True)
class ResumenBase:
    """DTO base de un reporte con totales y desglose."""
    total_ventas: float
    total_pagos: float
    diferencia: float


# =========================
# Utilidades internas
# =========================

def _stopwatch() -> Tuple[callable, callable]:
    """
    Pequeño cronómetro. Uso:
        start, stop = _stopwatch(); start(); ...; ms = stop()
    """
    t0 = 0.0

    def start():
        nonlocal t0
        t0 = perf_counter()

    def stop() -> int:
        # retorna milisegundos
        return int((perf_counter() - t0) * 1000)

    return start, stop


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asegura la presencia de claves esperadas y normaliza tipos sencillos.
    Se asume que el form ya validó; esto da defaults conservadores.
    """
    return {
        "fecha_desde": params.get("fecha_desde"),
        "fecha_hasta": params.get("fecha_hasta"),
        "sucursal_id": params.get("sucursal_id"),
        "metodos": params.get("metodos") or [],
        "estados": params.get("estados") or [],
        "turno_id": params.get("turno_id"),
        "granularidad": params.get("granularidad"),
    }


def _daterange_from_params(params: Dict[str, Any]) -> DateRange:
    # params vienen como ISO strings; el form genera eso.
    from datetime import date as _date
    d1 = _date.fromisoformat(params["fecha_desde"])
    d2 = _date.fromisoformat(params["fecha_hasta"])
    return DateRange(desde=d1, hasta=d2)


def _resolve_sucursal(empresa: Any, sucursal_id: Optional[int]) -> Optional[Any]:
    """Evita acoplar al modelo concreto: se importa on-demand."""
    if not sucursal_id:
        return None
    from apps.org.models import Sucursal
    try:
        return Sucursal.objects.get(empresa=empresa, id=sucursal_id)
    except Sucursal.DoesNotExist:
        return None


def _resolve_turno(empresa: Any, turno_id: Optional[int]) -> Optional[Any]:
    if not turno_id:
        return None
    from apps.cashbox.models import TurnoCaja
    try:
        return TurnoCaja.objects.get(empresa=empresa, id=turno_id)
    except TurnoCaja.DoesNotExist:
        return None


# =============================================================================
# Contrato de SELECTORS esperados (resumen)
# -----------------------------------------------------------------------------
# sales_selectors:
#   - ventas_por_dia(empresa, sucursal, dr: DateRange, estados: list[str] | None) -> QS[dict]
#       .values('fecha').annotate(total_monto, ventas, total_items, ticket_promedio)
#   - ventas_por_turno(empresa, sucursal, dr: DateRange) -> QS[dict]
#       .values('turno_id', 'sucursal__nombre', 'abierto_en', 'cerrado_en')
#       .annotate(ventas, total_ventas)
#   - ventas_mensual_por_sucursal(empresa, dr: DateRange) -> QS[dict]
#       .values('anio', 'mes', 'sucursal__nombre').annotate(ventas, total_ventas, ticket_promedio)
#
# payments_selectors:
#   - pagos_por_metodo(empresa, sucursal, dr: DateRange, metodo_ids: list[int] | None) -> QS[dict]
#       .values('metodo__nombre').annotate(total, propinas)
#   - ingresos_mensuales_por_metodo(empresa, dr: DateRange) -> QS[dict]
#       .values('anio', 'mes', 'metodo__nombre').annotate(total, propinas)
#   - propinas_por_usuario(empresa, dr: DateRange) -> QS[dict]
#       .values('usuario__username').annotate(propinas)
#
# cashbox_selectors:
#   - cierres_por_dia(empresa, sucursal, dr: DateRange) -> QS[dict]
#       .values('fecha', 'sucursal__nombre').annotate(total_teorico, total_real)
#   - totales_por_turno(empresa, sucursal, dr: DateRange) -> QS[dict]
#       .values('turno_id', 'medio__nombre').annotate(monto, propinas)
# =============================================================================


# =========================
# Reportes operativos
# =========================

def resumen_diario(*, empresa: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consolida:
      - Ventas por día (cantidad, total, items, ticket promedio)
      - Pagos por método
      - Diferencia simple total_ventas - total_pagos (control grueso)
    """
    p = _normalize_params(params)
    dr = _daterange_from_params(p)
    sucursal = _resolve_sucursal(empresa, p["sucursal_id"])

    start, stop = _stopwatch()
    start()

    # Ventas por día
    ventas_qs = sales_sel.ventas_por_dia(
        empresa=empresa,
        sucursal=sucursal,
        dr=dr,
        estados=p["estados"] or None,
    )
    ventas_series: List[SerieDia] = list(ventas_qs)

    # Pagos por método
    pagos_qs = pay_sel.pagos_por_metodo(
        empresa=empresa,
        sucursal=sucursal,
        dr=dr,
        metodo_ids=p["metodos"] or None,
    )
    pagos: List[MetodoResumen] = list(pagos_qs)

    # Totales
    total_ventas = float(sum(row.get("total_monto", 0)
                         or 0 for row in ventas_series))
    total_pagos = float(sum(row.get("total", 0) or 0 for row in pagos))
    diff = round(total_ventas - total_pagos, 2)

    duration_ms = stop()

    return {
        "meta": {
            "report_type": m_reports.ReportType.SALES_DAILY,
            "duration_ms": duration_ms,
            "params": p,
        },
        "totales": {
            "total_ventas": total_ventas,
            "total_pagos": total_pagos,
            "diferencia": diff,
        },
        "ventas_por_dia": ventas_series,
        "pagos_por_metodo": pagos,
    }


def pagos_por_metodo(*, empresa: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reporte directo de pagos por método con total + propinas.
    """
    p = _normalize_params(params)
    dr = _daterange_from_params(p)
    sucursal = _resolve_sucursal(empresa, p["sucursal_id"])

    start, stop = _stopwatch()
    start()
    pagos_qs = pay_sel.pagos_por_metodo(
        empresa=empresa, sucursal=sucursal, dr=dr, metodo_ids=p["metodos"] or None
    )
    rows: List[MetodoResumen] = list(pagos_qs)
    duration_ms = stop()

    total = float(sum(r.get("total", 0) or 0 for r in rows))
    propinas = float(sum(r.get("propinas", 0) or 0 for r in rows))

    return {
        "meta": {
            "report_type": m_reports.ReportType.PAYMENTS_BY_METHOD,
            "duration_ms": duration_ms,
            "params": p,
        },
        "totales": {"total": total, "propinas": propinas},
        "detalle": rows,
    }


def ventas_por_turno(*, empresa: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ventas agrupadas por TurnoCaja + composición por método (monto/propinas).
    """
    p = _normalize_params(params)
    dr = _daterange_from_params(p)
    sucursal = _resolve_sucursal(empresa, p["sucursal_id"])

    start, stop = _stopwatch()
    start()
    # Ventas por turno
    rows_qs = sales_sel.ventas_por_turno(
        empresa=empresa, sucursal=sucursal, dr=dr)
    rows: List[TurnoResumen] = list(rows_qs)

    # Pagos por método (mismo rango + sucursal)
    pagos_qs = pay_sel.pagos_por_metodo(
        empresa=empresa,
        sucursal=sucursal,
        dr=dr,
        metodo_ids=p["metodos"] or None,
    )
    pagos = list(pagos_qs)
    duration_ms = stop()

    total_ventas = float(sum(r.get("total_ventas", 0) or 0 for r in rows))
    cant_ventas = int(sum(r.get("ventas", 0) or 0 for r in rows))
    propinas = float(sum(r.get("propinas", 0) or 0 for r in pagos))

    return {
        "meta": {
            "report_type": m_reports.ReportType.SALES_BY_SHIFT,
            "duration_ms": duration_ms,
            "params": p,
        },
        "totales": {
            "total_ventas": total_ventas,
            "ventas": cant_ventas,
            "total_teorico": total_ventas,  # alias claro para UI de Caja
            "propinas": propinas,
        },
        "por_turno": rows,             # ← antes ya lo teníamos
        "metodos": pagos,              # ← ahora lo añadimos
    }


# =========================
# Consolidados
# =========================

# apps/reports/services/reports.py

def mensual_por_sucursal(*, empresa: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consolidado mensual de ventas por sucursal.
    Selector devuelve filas por (anio, mes, sucursal__nombre). Aquí agregamos:
      - series_mensual: por (anio, mes) (consolidado total)
      - por_sucursal_resumen: total por sucursal en el período
      - totales extendidos: total_vendido y ticket_promedio global
    """
    p = _normalize_params(params)
    dr = _daterange_from_params(p)

    start, stop = _stopwatch()
    start()
    rows_qs = sales_sel.ventas_mensual_por_sucursal(empresa=empresa, dr=dr)
    rows = list(rows_qs)
    duration_ms = stop()

    # Totales globales
    total_ventas = float(sum(r.get("total_ventas", 0) or 0 for r in rows))
    ventas_count = int(sum(r.get("ventas", 0) or 0 for r in rows))
    ticket_promedio_global = round(
        total_ventas / ventas_count, 2) if ventas_count > 0 else 0.0

    # Serie mensual (consolidar todas las sucursales por (anio, mes))
    by_month = {}
    for r in rows:
        key = (int(r["anio"]), int(r["mes"]))
        bm = by_month.setdefault(
            key, {"anio": key[0], "mes": key[1], "ventas": 0, "total_ventas": 0.0})
        bm["ventas"] += int(r.get("ventas", 0) or 0)
        bm["total_ventas"] += float(r.get("total_ventas", 0) or 0)

    series_mensual = []
    for (a, m) in sorted(by_month.keys()):
        data = by_month[(a, m)]
        v = data["ventas"]
        tv = data["total_ventas"]
        data["ticket_promedio"] = round(tv / v, 2) if v > 0 else 0.0
        series_mensual.append(data)

    # Resumen por sucursal en todo el período
    by_branch = {}
    for r in rows:
        name = r["sucursal__nombre"] or "—"
        bb = by_branch.setdefault(name, {"nombre": name, "total_ventas": 0.0})
        bb["total_ventas"] += float(r.get("total_ventas", 0) or 0)

    por_sucursal_resumen = sorted(
        by_branch.values(), key=lambda x: x["nombre"])

    return {
        "meta": {
            "report_type": m_reports.ReportType.SALES_MONTHLY,
            "duration_ms": duration_ms,
            "params": p,
        },
        # mantenemos claves antiguas + añadimos las que el template espera
        "totales": {
            "total_ventas": total_ventas,
            "ventas": ventas_count,
            "total_vendido": total_ventas,           # alias amigable para UI
            "ticket_promedio": ticket_promedio_global,
        },
        "detalle": rows,                  # por (anio, mes, sucursal)
        "series_mensual": series_mensual,  # por (anio, mes) consolidado
        "por_sucursal_resumen": por_sucursal_resumen,  # por sucursal
    }


# =========================
# Dataset genérico para exportación
# =========================

def build_dataset(
    *,
    report_type: m_reports.ReportType | str,
    empresa: Any,
    params: Dict[str, Any],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Devuelve (columns, rows) listos para los exportadores.
    - columns: nombres de columnas en orden
    - rows: lista de dicts (todas las filas comparten claves compatibles)
    """
    rt = m_reports.ReportType(
        report_type) if report_type in m_reports.ReportType.values else report_type
    p = _normalize_params(params)

    if rt == m_reports.ReportType.SALES_DAILY:
        data = resumen_diario(empresa=empresa, params=p)
        # Serie por día
        cols = ["fecha", "ventas", "total_items",
                "total_monto", "ticket_promedio"]
        rows = data["ventas_por_dia"]
        return cols, rows

    if rt == m_reports.ReportType.PAYMENTS_BY_METHOD:
        data = pagos_por_metodo(empresa=empresa, params=p)
        cols = ["metodo", "total", "propinas"]
        rows = data["detalle"]
        return cols, rows

    if rt == m_reports.ReportType.SALES_BY_SHIFT:
        data = ventas_por_turno(empresa=empresa, params=p)
        cols = ["turno_id", "sucursal", "abierto_en",
                "cerrado_en", "ventas", "total_ventas"]
        rows = data["por_turno"]
        return cols, rows

    if rt == m_reports.ReportType.SALES_MONTHLY:
        data = mensual_por_sucursal(empresa=empresa, params=p)
        cols = ["anio", "mes", "sucursal__nombre",
                "ventas", "total_ventas", "ticket_promedio"]
        rows = data["detalle"]
        return cols, rows

    # Si se pide un tipo aún no implementado explícitamente,
    # devolvemos estructura vacía pero con contrato válido.
    return [], []


# =========================
# Helper para registrar export (opcional, llamado desde la vista)
# =========================

def create_export_log(
    *,
    empresa: Any,
    requested_by: Any,
    report_type: m_reports.ReportType | str,
    fmt: m_reports.ExportFormat | str,
    params: Dict[str, Any],
    file=None,
    row_count: int = 0,
    duration_ms: int = 0,
    status: m_reports.ExportStatus | str = m_reports.ExportStatus.DONE,
    error_message: str = "",
    saved_report: Optional[m_reports.SavedReport] = None,
) -> m_reports.ReportExport:
    """
    Crea un registro en ReportExport. Útil para ser invocado por los exportadores
    o por la vista después de generar el archivo.
    """
    rexp = m_reports.ReportExport.objects.create(
        empresa=empresa,
        saved_report=saved_report,
        report_type=str(report_type),
        params=params,
        fmt=str(fmt),
        file=file,
        row_count=row_count,
        duration_ms=duration_ms,
        status=str(status),
        error_message=error_message or "",
        requested_by=requested_by,
    )
    return rexp
