from django.contrib import admin
from .models import Vehiculo, TipoVehiculo


@admin.register(TipoVehiculo)
class TipoVehiculoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "slug", "activo")
    list_filter = ("empresa", "activo")
    search_fields = ("nombre", "slug")
    autocomplete_fields = ("empresa",)
    ordering = ("nombre",)


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ("patente", "empresa", "cliente", "tipo",
                    "marca", "modelo", "anio", "activo", "actualizado")
    list_filter = ("empresa", "activo", "tipo", "anio")
    search_fields = ("patente", "marca", "modelo",
                     "cliente__nombre", "cliente__apellido")
    autocomplete_fields = ("empresa", "cliente", "tipo")
    readonly_fields = ("creado", "actualizado")
    ordering = ("-actualizado",)
