# apps/customers/admin.py
from django.contrib import admin
from .models import Cliente, ClienteFacturacion


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "display_name", "empresa", "documento", "email", "tel_wpp", "activo", "creado"
    )
    list_filter = ("activo", "empresa", "tipo_persona")
    search_fields = ("nombre", "apellido", "razon_social",
                     "documento", "email", "tel_wpp")
    autocomplete_fields = ("empresa", "creado_por")
    ordering = ("razon_social", "apellido", "nombre")


@admin.register(ClienteFacturacion)
class ClienteFacturacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "cond_iva", "cuit", "modificado")
    search_fields = ("cliente__nombre", "cliente__razon_social", "cuit")
    autocomplete_fields = ("cliente",)
