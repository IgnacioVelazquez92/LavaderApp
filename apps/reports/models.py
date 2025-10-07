# apps/reports/models.py
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# =========================
# Enums / Choices del módulo
# =========================

class ReportType(models.TextChoices):
    """
    Catálogo de reportes soportados por el módulo.
    ⚠️ Importante: este enum describe "qué" se quiere ver, no "cómo" se calcula.
    La lógica vive en selectors/services, no se mezcla en los modelos.
    """
    # Operativos (día/turno)
    SALES_DAILY = "sales_daily", _("Ventas por día")
    SALES_BY_SHIFT = "sales_by_shift", _("Ventas por turno de caja")
    PAYMENTS_BY_METHOD = "payments_by_method", _("Pagos por método")
    TIPS_BY_USER = "tips_by_user", _("Propinas por usuario")
    CASHBOX_CLOSURES = "cashbox_closures", _("Cierres de caja (Z)")

    # Consolidados
    SALES_MONTHLY = "sales_monthly", _("Ventas mensuales")
    SALES_BY_BRANCH = "sales_by_branch", _("Ventas por sucursal")
    INCOME_METHOD_MONTHLY = "income_method_monthly", _(
        "Ingresos por método (mensual)")
    TOP_SERVICES = "top_services", _("Servicios más vendidos")

    # Analíticos / KPI pack
    CONSOLIDATED_KPIS = "consolidated_kpis", _("KPIs consolidados")
    TIMESERIES = "timeseries", _("Series temporales")


class ExportFormat(models.TextChoices):
    """
    Formatos de exportación disponibles.
    El formateo se implementa en apps/reports/exports/*.py
    """
    XLSX = "xlsx", "Excel"
    CSV = "csv", "CSV"
    PDF = "pdf", "PDF"


class ExportStatus(models.TextChoices):
    """Estado final de una exportación (auditoría)."""
    DONE = "done", _("Completado")
    FAILED = "failed", _("Fallido")


# =========================
# Modelos principales
# =========================

class SavedReport(models.Model):
    """
    Preset reutilizable de un reporte con sus filtros y alcance de tenencia.
    - No almacena resultados, solo la "intención" de consulta (params serializables).
    - Soporta visibilidad privada/pública dentro de la empresa.
    - Se puede acotar a una sucursal (opcional).
    """
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="reports_saved",
        help_text=_("Empresa a la que pertenece este preset."),
    )
    sucursal = models.ForeignKey(
        "org.Sucursal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_saved",
        help_text=_("Sucursal opcional para acotar por defecto el preset."),
    )
    nombre = models.CharField(
        max_length=120,
        validators=[MinLengthValidator(3)],
        db_index=True,
        help_text=_(
            "Nombre legible del preset (único por autor dentro de la empresa)."),
    )
    report_type = models.CharField(
        max_length=64,
        choices=ReportType.choices,
        db_index=True,
        help_text=_("Tipo de reporte que renderizarán los services y vistas."),
    )
    # Ejemplo típico:
    # {
    #   "fecha_desde": "2025-10-01",
    #   "fecha_hasta": "2025-10-05",
    #   "estado": ["pagado", "terminado"],
    #   "metodo": ["EFECTIVO", "TARJETA"],
    #   "turno_id": null,
    #   "granularidad": "dia"
    # }
    params = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Parámetros serializables del reporte (filtros y opciones)."),
    )
    is_public = models.BooleanField(
        default=False,
        help_text=_(
            "Si es público, cualquier usuario de la empresa puede usar este preset."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_created",
        help_text=_("Usuario que creó el preset."),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_updated",
        null=True,
        blank=True,
        help_text=_("Último usuario que modificó el preset."),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reports_saved_report"
        verbose_name = _("Reporte guardado (preset)")
        verbose_name_plural = _("Reportes guardados (presets)")
        ordering = ("-created_at", "nombre")
        constraints = [
            # Evita duplicar nombres de presets por autor dentro de la misma empresa.
            models.UniqueConstraint(
                fields=("empresa", "created_by", "nombre"),
                name="uniq_sr_emp_author_name",  # <= 30 chars
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "report_type"],
                         name="idx_sr_emp_rtype"),  # <= 30 chars
            models.Index(fields=["empresa", "sucursal"],
                         name="idx_sr_emp_suc"),       # <= 30 chars
        ]

    def __str__(self) -> str:
        scope = f" / {self.sucursal.nombre}" if self.sucursal_id else ""
        return f"[{self.empresa}]{scope} · {self.nombre} · {self.get_report_type_display()}"

    # ---------- Helpers opcionales ----------

    def to_human_scope(self) -> str:
        """Descripción corta del alcance por defecto del preset (empresa / sucursal)."""
        if self.sucursal_id:
            return f"{self.empresa} / {self.sucursal}"
        return f"{self.empresa}"

    def safe_params(self) -> dict:
        """
        Devuelve params garantizando un dict (nunca None).
        Los forms/filters son responsables de validar su contrato.
        """
        return self.params or {}


class ReportExport(models.Model):
    """
    Bitácora de exportaciones de reportes: qué, cuándo, quién, cómo y cuánto tardó.
    - Permite auditar descargas y re-descargar archivos desde la UI.
    - No es un 'cache' de datasets: es un registro (histórico) de exportaciones efectivas.
    """
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="reports_exports",
        help_text=_("Empresa dueña de la exportación."),
    )
    saved_report = models.ForeignKey(
        SavedReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exports",
        help_text=_(
            "Preset asociado (si la exportación proviene de un reporte guardado)."),
    )
    report_type = models.CharField(
        max_length=64,
        choices=ReportType.choices,
        db_index=True,
        help_text=_("Tipo de reporte exportado."),
    )
    params = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Parámetros usados al momento de exportar (se registran para auditoría)."),
    )
    fmt = models.CharField(
        max_length=8,
        choices=ExportFormat.choices,
        default=ExportFormat.XLSX,
        db_index=True,
        help_text=_("Formato de archivo exportado."),
    )
    file = models.FileField(
        upload_to="reports/exports/%Y/%m/%d/",
        null=True,
        blank=True,
        help_text=_(
            "Archivo generado (si aplica). Puede ser omitido en fallos."),
    )
    row_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Cantidad de filas exportadas (si el formato lo admite)."),
    )
    duration_ms = models.PositiveIntegerField(
        default=0,
        help_text=_(
            "Tiempo de generación en milisegundos (métrica de performance)."),
    )
    status = models.CharField(
        max_length=12,
        choices=ExportStatus.choices,
        default=ExportStatus.DONE,
        db_index=True,
        help_text=_("Estado final de la exportación."),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text=_("Mensaje de error si la exportación falló."),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_exports_requested",
        help_text=_("Usuario que solicitó la exportación."),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "reports_export"
        verbose_name = _("Exportación de reporte")
        verbose_name_plural = _("Exportaciones de reportes")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["empresa", "report_type", "fmt"],
                         name="idx_re_emp_typ_fmt"),  # <= 30 chars
            # <= 30 chars
            models.Index(fields=["empresa", "status"], name="idx_re_emp_stat"),
        ]

    def __str__(self) -> str:
        ts = timezone.localtime(self.created_at).strftime("%Y-%m-%d %H:%M")
        return f"{self.get_report_type_display()} → {self.fmt.upper()} ({ts})"

    # ---------- Helpers opcionales ----------

    @property
    def ok(self) -> bool:
        """True si la exportación terminó correctamente."""
        return self.status == ExportStatus.DONE

    def filename_suggested(self) -> str:
        """
        Nombre de archivo sugerido para descarga (no muta el FileField).
        Ej.: sales_daily_2025-10-05_153012.xlsx
        """
        ts = timezone.localtime(self.created_at).strftime("%Y-%m-%d_%H%M%S")
        return f"{self.report_type}_{ts}.{self.fmt}"
