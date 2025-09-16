# apps/app_log/admin.py
"""
Configuración de Django Admin para AppLog y AuditLog.
"""

from django.contrib import admin
from .models import AppLog, AuditLog


@admin.register(AppLog)
class AppLogAdmin(admin.ModelAdmin):
    list_display = (
        "creado_en",
        "nivel",
        "http_status",
        "origen",
        "evento",
        "http_method",
        "http_path",
        "username",
        "empresa_id",
    )
    list_filter = ("nivel", "origen", "evento", "http_status", "creado_en")
    search_fields = ("mensaje", "http_path", "username", "meta_json")
    ordering = ("-creado_en",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "creado_en",
        "action",
        "resource_type",
        "resource_id",
        "username",
        "empresa_id",
        "success",
    )
    list_filter = ("action", "resource_type", "success", "creado_en")
    search_fields = ("resource_id", "username", "changes",
                     "snapshot_before", "snapshot_after")
    ordering = ("-creado_en",)
