# apps/notifications/admin.py
from django.contrib import admin
from .models import PlantillaNotif, LogNotif, Canal, EstadoEnvio


@admin.register(PlantillaNotif)
class PlantillaNotifAdmin(admin.ModelAdmin):
    list_display = (
        "clave",
        "empresa",
        "canal",
        "activo",
        "creado_por",
        "creado_en",
    )
    list_filter = ("empresa", "canal", "activo", "creado_en")
    search_fields = ("clave", "cuerpo_tpl", "asunto_tpl")
    autocomplete_fields = ("empresa", "creado_por")
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        (None, {"fields": ("empresa", "clave", "canal", "activo")}),
        ("Contenido", {"fields": ("asunto_tpl", "cuerpo_tpl")}),
        ("Auditoría", {
         "fields": ("creado_por", "creado_en", "actualizado_en")}),
    )


@admin.register(LogNotif)
class LogNotifAdmin(admin.ModelAdmin):
    list_display = (
        "enviado_en",
        "empresa",
        "venta",
        "canal",
        "destinatario",
        "estado",
    )
    list_filter = ("empresa", "canal", "estado", "enviado_en")
    search_fields = ("destinatario", "asunto_renderizado",
                     "cuerpo_renderizado", "error_msg", "idempotency_key")
    autocomplete_fields = ("empresa", "venta", "plantilla", "creado_por")
    readonly_fields = (
        "empresa",
        "venta",
        "plantilla",
        "canal",
        "destinatario",
        "asunto_renderizado",
        "cuerpo_renderizado",
        "estado",
        "error_msg",
        "enviado_en",
        "idempotency_key",
        "meta",
        "creado_por",
    )
    fieldsets = (
        (None, {"fields": ("empresa", "venta", "plantilla")}),
        ("Datos de envío", {"fields": (
            "canal", "destinatario", "asunto_renderizado", "cuerpo_renderizado")}),
        ("Estado", {"fields": ("estado", "error_msg", "enviado_en")}),
        ("Extra", {"fields": ("idempotency_key", "meta")}),
        ("Auditoría", {"fields": ("creado_por",)}),
    )

    def has_add_permission(self, request):
        # Los logs se crean desde los services; no desde el admin.
        return False
