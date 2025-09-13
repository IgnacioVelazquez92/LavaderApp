# apps/pricing/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

from .models import PrecioServicio


class VigenciaAbiertaFilter(admin.SimpleListFilter):
    title = "vigencia abierta"
    parameter_name = "vig_abierta"

    def lookups(self, request, model_admin):
        return (("1", "Sí"), ("0", "No"))

    def queryset(self, request, queryset):
        val = self.value()
        if val == "1":
            return queryset.filter(vigencia_fin__isnull=True)
        if val == "0":
            return queryset.exclude(vigencia_fin__isnull=True)
        return queryset


class VigenteHoyFilter(admin.SimpleListFilter):
    title = "vigente hoy"
    parameter_name = "vig_hoy"

    def lookups(self, request, model_admin):
        return (("1", "Sí"),)

    def queryset(self, request, queryset):
        if self.value() == "1":
            hoy = timezone.localdate()
            return queryset.filter(
                activo=True,
                vigencia_inicio__lte=hoy
            ).filter(vigencia_fin__isnull=True) | queryset.filter(
                activo=True,
                vigencia_inicio__lte=hoy,
                vigencia_fin__gte=hoy
            )
        return queryset


@admin.register(PrecioServicio)
class PrecioServicioAdmin(admin.ModelAdmin):
    list_display = (
        "empresa", "sucursal", "servicio", "tipo_vehiculo",
        "moneda", "precio", "vigencia_inicio", "vigencia_fin",
        "activo", "actualizado",
    )
    list_filter = (
        "empresa", "sucursal", "servicio", "tipo_vehiculo",
        "moneda", "activo", VigenciaAbiertaFilter, VigenteHoyFilter,
    )
    search_fields = (
        "empresa__nombre", "sucursal__nombre",
        "servicio__nombre", "tipo_vehiculo__nombre",
    )
    date_hierarchy = "vigencia_inicio"
    ordering = ("-actualizado",)
    autocomplete_fields = ("empresa", "sucursal", "servicio", "tipo_vehiculo")
    readonly_fields = ("creado", "actualizado")

    actions = ("cerrar_vigencia_hoy", "marcar_inactivo")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("empresa", "sucursal", "servicio", "tipo_vehiculo")

    @admin.action(description="Cerrar vigencia al día de hoy")
    def cerrar_vigencia_hoy(self, request, queryset):
        hoy = timezone.localdate()
        updated = queryset.filter(
            vigencia_fin__isnull=True).update(vigencia_fin=hoy)
        self.message_user(
            request, f"Vigencia cerrada hoy en {updated} registro(s).")

    @admin.action(description="Marcar como inactivo")
    def marcar_inactivo(self, request, queryset):
        updated = queryset.filter(activo=True).update(activo=False)
        self.message_user(
            request, f"Marcados como inactivos {updated} registro(s).")
