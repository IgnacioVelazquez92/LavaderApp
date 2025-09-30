# apps/sales/admin.py
from .models import Promotion
from django.contrib import admin
from .models import Venta, VentaItem


class VentaItemInline(admin.TabularInline):
    model = VentaItem
    extra = 0
    readonly_fields = ("precio_unitario", "creado", "actualizado")


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cliente",
        "vehiculo",
        "estado",          # proceso
        "payment_status",  # pago (nuevo en el modelo)
        "subtotal",
        "total",
        "saldo_pendiente",
        "creado",
    )
    list_filter = ("estado", "payment_status", "sucursal", "empresa")
    search_fields = ("id", "cliente__nombre", "vehiculo__patente")
    inlines = [VentaItemInline]
    readonly_fields = ("creado", "actualizado")


@admin.register(VentaItem)
class VentaItemAdmin(admin.ModelAdmin):
    list_display = ("venta", "servicio", "cantidad",
                    "precio_unitario", "subtotal_col")
    list_filter = ("servicio",)
    search_fields = ("venta__id", "servicio__nombre")
    readonly_fields = ("creado", "actualizado")

    def subtotal_col(self, obj):
        return obj.subtotal
    subtotal_col.short_description = "Subtotal"


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "sucursal", "scope", "mode",
                    "value", "activo", "prioridad", "valido_desde", "valido_hasta")
    list_filter = ("empresa", "sucursal", "scope", "mode", "activo")
    search_fields = ("nombre", "codigo")
