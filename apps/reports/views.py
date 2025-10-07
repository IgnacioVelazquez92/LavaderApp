# apps/reports/views.py
from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from typing import Any, Dict, Tuple

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View

from apps.org.permissions import Perm

from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm
from .forms.filters import ReportFilterForm
from . import models as m_reports
from .services import reports as svc


# ============================================================================
# Helpers internos
# ============================================================================

def _empresa(request: HttpRequest):
    """
    Lee la empresa activa del request (TenancyMiddleware).
    Este helper evita acoplar las vistas a cómo se inyecta en el request.
    """
    emp = getattr(request, "empresa_activa", None)
    if emp is None:
        # En tu proyecto normalmente siempre habrá empresa; si no, 403/redirect
        raise Http404("Empresa no encontrada en el contexto de la solicitud.")
    return emp


def _render_filters_and_context(
    *, request: HttpRequest, form: ReportFilterForm, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convención para preparar el contexto de template:
    - form: formulario de filtros (reutilizable)
    - payload: estructura devuelta por el service (meta, totales, desgloses)
    """
    return {
        "form": form,
        "filters": _filters_display(form),  # <- chips seguros
        **(payload or {}),
    }


def _filters_display(form: ReportFilterForm) -> Dict[str, Any]:
    """
    Devuelve etiquetas 'seguras' para los chips de filtros,
    sin depender de cleaned_data desde el template.
    """
    # Si es válido, usamos cleaned_data
    if form.is_valid():
        cd = form.cleaned_data
        return {
            "desde": cd.get("fecha_desde"),
            "hasta": cd.get("fecha_hasta"),
            "sucursal_label": str(cd["sucursal"]) if cd.get("sucursal") else "",
            "metodos_count": len(cd.get("metodos") or []),
            "estados_count": len(cd.get("estados") or []),
            "turno_label": f"#{cd['turno'].pk}" if cd.get("turno") else "",
        }

    # Si NO es válido o está parcialmente bound, usamos su default interno
    try:
        dr = form._build_initial_daterange()  # ya lo tenés implementado
        desde, hasta = dr.desde, dr.hasta
    except Exception:
        desde = hasta = ""

    return {
        "desde": desde,
        "hasta": hasta,
        "sucursal_label": "",
        "metodos_count": 0,
        "estados_count": 0,
        "turno_label": "",
    }


# ============================================================================
# Vistas de consulta (server-rendered con Bootstrap)
# ============================================================================

class BaseReportView(EmpresaPermRequiredMixin, TemplateView):
    """
    Base para vistas de reportes con:
    - Tenancy + permisos
    - Manejo de ReportFilterForm
    - Método abstracto 'build_payload' que invoca el service
    """
    required_perms = (Perm.REPORTS_VIEW,)
    template_name = ""  # cada subclase debe asignarlo

    # Permite a subclases ajustar initial del form (por ejemplo granularidad)
    def default_initial(self) -> Dict[str, Any]:
        return {}

    def build_payload(self, *, empresa, params: Dict[str, Any]) -> Dict[str, Any]:
        """Subclases deben implementar la invocación al service."""
        raise NotImplementedError

    def get(self, request, *args, **kwargs) -> HttpResponse:
        empresa = _empresa(request)
        initial = self.default_initial()
        form = ReportFilterForm(request.GET or None,
                                request=request, initial=initial)

        payload: Dict[str, Any] = {}
        if form.is_valid():
            params = form.to_params()
            payload = self.build_payload(empresa=empresa, params=params)
        else:
            # Cuando el form no es válido, devolvemos la UI con errores inline
            messages.warning(request, _("Revisá los filtros del reporte."))

        ctx = _render_filters_and_context(
            request=request, form=form, payload=payload)
        return self.render_to_response(ctx)


class SalesDailyView(BaseReportView):
    """
    Reporte: Ventas por día + pagos por método + diferencia
    """
    template_name = "reports/sales_daily.html"

    def build_payload(self, *, empresa, params: Dict[str, Any]) -> Dict[str, Any]:
        return svc.resumen_diario(empresa=empresa, params=params)


class PaymentsByMethodView(BaseReportView):
    """
    Reporte: Pagos agrupados por método (monto + propinas)
    """
    template_name = "reports/payments_by_method.html"

    def build_payload(self, *, empresa, params: Dict[str, Any]) -> Dict[str, Any]:
        return svc.pagos_por_metodo(empresa=empresa, params=params)


class SalesByShiftView(BaseReportView):
    """
    Reporte: Ventas agrupadas por Turno de Caja
    """
    template_name = "reports/cashbox_summary.html"

    def build_payload(self, *, empresa, params: Dict[str, Any]) -> Dict[str, Any]:
        return svc.ventas_por_turno(empresa=empresa, params=params)


class MonthlyConsolidatedView(BaseReportView):
    """
    Reporte: Consolidado mensual por sucursal (ventas, tickets, ticket promedio)
    """
    template_name = "reports/monthly_consolidated.html"

    def default_initial(self) -> Dict[str, Any]:
        # Sugerimos granularidad "mes" por defecto para esta vista
        return {"granularidad": "mes"}

    def build_payload(self, *, empresa, params: Dict[str, Any]) -> Dict[str, Any]:
        return svc.mensual_por_sucursal(empresa=empresa, params=params)


# ============================================================================
# Exportación (CSV/XLSX/PDF)
# - Esta vista sirve como endpoint único de export (evita duplicación).
# - Construye dataset via services.reports.build_dataset(...)
# - Llama exportadores en apps/reports/exports/*
# - Registra ReportExport para auditoría (OK o Fail).
# ============================================================================

class ExportReportView(EmpresaPermRequiredMixin, View):
    """
    Endpoint: /reports/export/?type=<ReportType>&format=<xlsx|csv|pdf>&...
    Requiere 'REPORTS_EXPORT'. Usa los mismos filtros que las vistas de consulta.
    """
    required_perms = (Perm.REPORTS_EXPORT,)

    def get(self, request, *args, **kwargs) -> HttpResponse:
        empresa = _empresa(request)

        # 1) Parseo de tipo y formato
        rtype = request.GET.get("type")
        fmt = request.GET.get("format", "xlsx").lower()
        if not rtype:
            messages.error(request, _(
                "Falta el parámetro 'type' del reporte."))
            raise Http404

        # 2) Validación de filtros (reutilizamos ReportFilterForm)
        form = ReportFilterForm(request.GET or None, request=request)
        if not form.is_valid():
            messages.error(request, _("Filtros inválidos para exportar."))
            # Sugerimos volver a la URL referer si existe:
            return redirect(request.META.get("HTTP_REFERER", reverse("reports:sales_daily")))

        params = form.to_params()

        # 3) Construcción del dataset (columns, rows)
        try:
            columns, rows = svc.build_dataset(
                report_type=rtype, empresa=empresa, params=params)
        except Exception as ex:
            # Registrar fallido desde el principio
            svc.create_export_log(
                empresa=empresa,
                requested_by=request.user,
                report_type=rtype,
                fmt=fmt,
                params=params,
                row_count=0,
                duration_ms=0,
                status=m_reports.ExportStatus.FAILED,
                error_message=str(ex),
            )
            messages.error(request, _(
                "No se pudo construir el dataset del reporte."))
            raise

        if not columns:
            # Si el dataset no está implementado para ese type, devolvemos 404
            svc.create_export_log(
                empresa=empresa,
                requested_by=request.user,
                report_type=rtype,
                fmt=fmt,
                params=params,
                row_count=0,
                duration_ms=0,
                status=m_reports.ExportStatus.FAILED,
                error_message="Dataset vacío o tipo no implementado.",
            )
            messages.error(request, _(
                "Reporte no disponible para exportación."))
            raise Http404("Reporte no implementado para export.")

        # 4) Llamar exportador según formato
        #    Los exportadores devuelven (filename, fileobj_or_bytes)
        try:
            if fmt == "csv":
                from .exports import csv as exp_csv
                filename, payload = exp_csv.export_csv(columns, rows)
                content_type = "text/csv; charset=utf-8"
                fileobj = BytesIO(payload if isinstance(
                    payload, (bytes, bytearray)) else payload.encode("utf-8"))

            elif fmt == "xlsx":
                from .exports import excel as exp_xlsx
                filename, fileobj = exp_xlsx.export_xlsx(
                    columns, rows)  # retorna BytesIO/archivo
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            elif fmt == "pdf":
                from .exports import pdf as exp_pdf
                filename, fileobj = exp_pdf.export_pdf(
                    columns, rows, title=str(rtype))
                content_type = "application/pdf"

            else:
                messages.error(request, _(
                    "Formato de exportación no soportado."))
                raise Http404("Formato no soportado")
        except Exception as ex:
            svc.create_export_log(
                empresa=empresa,
                requested_by=request.user,
                report_type=rtype,
                fmt=fmt,
                params=params,
                row_count=len(rows),
                duration_ms=0,
                status=m_reports.ExportStatus.FAILED,
                error_message=str(ex),
            )
            raise

        # 5) Registrar export OK (sin persistir archivo en FileField; servimos streaming)
        svc.create_export_log(
            empresa=empresa,
            requested_by=request.user,
            report_type=rtype,
            fmt=fmt,
            params=params,
            row_count=len(rows),
            duration_ms=0,
            status=m_reports.ExportStatus.DONE,
            error_message="",
        )

        # 6) Responder archivo
        resp = FileResponse(fileobj, as_attachment=True,
                            filename=filename, content_type=content_type)
        # Cabeceras útiles:
        resp["Cache-Control"] = "no-store"
        return resp
