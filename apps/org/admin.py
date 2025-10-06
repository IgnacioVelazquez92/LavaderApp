# apps/org/admin.py

from django.contrib import admin
from .models import Empresa, EmpresaConfig, Sucursal


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "subdominio", "activo",
                    "cashbox_policy", "creado")
    search_fields = ("nombre", "subdominio")
    list_filter = ("activo", "creado", "cashbox_policy")
    ordering = ("-creado",)


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "codigo_interno", "creado")
    search_fields = ("nombre", "codigo_interno", "empresa__nombre")
    list_filter = ("empresa",)
    ordering = ("empresa", "nombre")


@admin.register(EmpresaConfig)
class EmpresaConfigAdmin(admin.ModelAdmin):
    list_display = ("empresa", "clave", "valor")
    search_fields = ("clave", "valor")
    list_filter = ("empresa",)
