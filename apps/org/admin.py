from django.contrib import admin
from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "creado", "actualizado")
    list_filter = ("activo",)
    search_fields = ("nombre",)
    ordering = ("nombre",)
