# apps/payments/admin.py
from django.contrib import admin
from .models import Pago, MedioPago


@admin.register(MedioPago)
class MedioPagoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "activo", "creado_en")
    list_filter = ("activo", "empresa")
    search_fields = ("nombre",)
    ordering = ("empresa", "nombre")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    """
    Admin de Pagos con MedioPago (FK).
    """
    list_display = (
        "id",
        "venta",
        "medio",
        "monto",
        "es_propina",
        "referencia",
        "creado_por",
        "creado_en",
    )
    list_filter = (
        "medio",
        "es_propina",
        "creado_por",
        ("creado_en", admin.DateFieldListFilter),
    )
    search_fields = ("referencia", "notas")
    date_hierarchy = "creado_en"
    ordering = ("-creado_en",)
    autocomplete_fields = ("venta", "creado_por", "medio")
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        (None, {"fields": ("venta", "medio", "monto", "es_propina")}),
        ("Opcionales", {"fields": ("referencia", "notas",
         "idempotency_key"), "classes": ("collapse",)}),
        ("Auditoría", {
         "fields": ("creado_por", "creado_en", "actualizado_en")}),
    )
