from django.contrib import admin

from .models import Comprobante, SecuenciaComprobante, ClienteFacturacion


@admin.register(SecuenciaComprobante)
class SecuenciaComprobanteAdmin(admin.ModelAdmin):
    list_display = ("sucursal", "tipo", "punto_venta",
                    "proximo_numero", "actualizado_en")
    list_filter = ("tipo", "sucursal", "punto_venta")
    search_fields = ("sucursal__nombre", "punto_venta")
    ordering = ("sucursal", "tipo", "punto_venta")


@admin.register(ClienteFacturacion)
class ClienteFacturacionAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "cuit", "empresa",
                    "cliente", "activo", "actualizado_en")
    list_filter = ("empresa", "activo")
    search_fields = ("razon_social", "cuit",
                     "cliente__nombre", "cliente__apellido")
    autocomplete_fields = ("empresa", "cliente")
    ordering = ("-actualizado_en", "razon_social")


@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo",
        "numero_completo",
        "empresa",
        "sucursal",
        "venta",
        "cliente",
        "total",
        "moneda",
        "emitido_en",
    )
    list_filter = ("tipo", "sucursal", "empresa", "moneda", "emitido_en")
    search_fields = ("id", "venta__id", "cliente__nombre",
                     "cliente__apellido", "cliente_facturacion__razon_social")
    readonly_fields = ("emitido_en", "numero_completo")
    autocomplete_fields = ("empresa", "sucursal", "venta",
                           "cliente", "cliente_facturacion", "emitido_por")
    fieldsets = (
        ("Identificación", {
            "fields": ("id", "tipo", "punto_venta", "numero", "numero_completo", "moneda", "total", "emitido_en")
        }),
        ("Vinculaciones", {
            "fields": ("empresa", "sucursal", "venta", "cliente", "cliente_facturacion", "emitido_por")
        }),
        ("Snapshot & Archivos", {
            "fields": ("snapshot", "archivo_html", "archivo_pdf")
        }),
    )
