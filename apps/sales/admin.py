# apps/sales/admin.py
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
        "estado",
        "subtotal",
        "total",
        "saldo_pendiente",
        "creado",
    )
    list_filter = ("estado", "sucursal", "empresa")
    search_fields = ("id", "cliente__nombre", "vehiculo__patente")
    inlines = [VentaItemInline]


@admin.register(VentaItem)
class VentaItemAdmin(admin.ModelAdmin):
    list_display = ("venta", "servicio", "cantidad",
                    "precio_unitario", "subtotal")
    list_filter = ("servicio",)
    search_fields = ("venta__id", "servicio__nombre")

    def subtotal(self, obj):
        return obj.subtotal
