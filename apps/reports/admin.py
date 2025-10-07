# apps/reports/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import SavedReport, ReportExport


# ---------- Helpers Tenancy (Admin) ----------
def _get_empresa_activa(request):
    """
    Intenta obtener la empresa activa inyectada por tu TenancyMiddleware.
    Si no existe (p.ej. en admin sin middleware), retorna None.
    """
    return getattr(request, "empresa_activa", None)


# ---------- Inlines (si más adelante querés ver exports desde el preset) ----------
class ReportExportInline(admin.TabularInline):
    model = ReportExport
    fk_name = "saved_report"
    extra = 0
    fields = (
        "created_at", "report_type", "fmt", "status", "row_count", "duration_ms", "file",
        "requested_by",
    )
    readonly_fields = (
        "created_at", "report_type", "fmt", "status", "row_count", "duration_ms", "file",
        "requested_by",
    )
    can_delete = False
    show_change_link = True


# ---------- SavedReport Admin ----------
@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "empresa", "sucursal", "report_type", "is_public",
        "created_by", "created_at",
    )
    list_filter = ("empresa", "sucursal", "report_type",
                   "is_public", "created_at")
    search_fields = ("nombre", "params")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")
    inlines = [ReportExportInline]

    actions = ("make_public", "make_private",)

    fieldsets = (
        (None, {
            "fields": (
                ("empresa", "sucursal"),
                "nombre",
                "report_type",
                "params",
                "is_public",
            )
        }),
        (_("Auditoría"), {
            "classes": ("collapse",),
            "fields": (("created_by", "updated_by"), ("created_at", "updated_at")),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        empresa = _get_empresa_activa(request)
        if empresa is not None and not request.user.is_superuser:
            qs = qs.filter(empresa=empresa)
        return qs.select_related("empresa", "sucursal", "created_by", "updated_by")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        empresa = _get_empresa_activa(request)
        if db_field.name in ("empresa", "sucursal") and empresa is not None and not request.user.is_superuser:
            if db_field.name == "empresa":
                kwargs["queryset"] = kwargs.get(
                    "queryset", db_field.remote_field.model.objects).filter(id=empresa.id)
            else:
                kwargs["queryset"] = kwargs.get(
                    "queryset", db_field.remote_field.model.objects).filter(empresa=empresa)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # --- Actions ---
    @admin.action(description=_("Marcar como público"))
    def make_public(self, request, queryset):
        updated = queryset.update(is_public=True)
        self.message_user(request, _(
            f"{updated} preset(s) marcados como públicos."), level=messages.SUCCESS)

    @admin.action(description=_("Marcar como privado"))
    def make_private(self, request, queryset):
        updated = queryset.update(is_public=False)
        self.message_user(request, _(
            f"{updated} preset(s) marcados como privados."), level=messages.SUCCESS)


# ---------- ReportExport Admin ----------
@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "empresa", "report_type", "fmt", "status",
        "row_count", "duration_ms", "requested_by", "file",
    )
    list_filter = (
        "empresa", "report_type", "fmt", "status", "created_at",
    )
    search_fields = ("error_message", "params")
    date_hierarchy = "created_at"
    readonly_fields = (
        "empresa", "saved_report", "report_type", "params", "fmt", "file",
        "row_count", "duration_ms", "status", "error_message",
        "requested_by", "created_at",
    )

    fieldsets = (
        (None, {
            "fields": (
                ("empresa", "saved_report"),
                ("report_type", "fmt", "status"),
                "params",
                ("row_count", "duration_ms"),
                "file",
            )
        }),
        (_("Auditoría"), {
            "classes": ("collapse",),
            "fields": (("requested_by", "created_at"), "error_message"),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        empresa = _get_empresa_activa(request)
        if empresa is not None and not request.user.is_superuser:
            qs = qs.filter(empresa=empresa)
        return qs.select_related("empresa", "saved_report", "requested_by")
