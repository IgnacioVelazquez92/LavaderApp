# apps/cashbox/admin.py
from __future__ import annotations
from .models import TurnoCaja, TurnoCajaTotal, CierreCaja, CierreCajaTotal

from decimal import Decimal
from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import localtime


class CierreCajaTotalInline(admin.TabularInline):
    model = CierreCajaTotal
    extra = 0
    can_delete = True
    fields = ("medio", "monto", "propinas", "total_incl_propina_display")
    readonly_fields = ("medio", "monto", "propinas",
                       "total_incl_propina_display")

    def total_incl_propina_display(self, obj: CierreCajaTotal):
        total = (obj.monto or Decimal("0")) + (obj.propinas or Decimal("0"))
        return f"{total:.2f}"
    total_incl_propina_display.short_description = "Total (incl. propina)"


@admin.register(CierreCaja)
class CierreCajaAdmin(admin.ModelAdmin):
    """
    Admin pensado para **auditoría**:
    - Cierre visible por empresa/sucursal y rango.
    - Inline de totales por método (read-only).
    - Campos calculados y formateo de estado.
    """

    list_display = (
        "id",
        "empresa",
        "sucursal",
        "abierto_en_local",
        "cerrado_en_local",
        "estado_badge",
        "usuario",
        "cerrado_por",
    )
    list_filter = (
        "empresa",
        "sucursal",
        ("abierto_en", admin.DateFieldListFilter),
        ("cerrado_en", admin.DateFieldListFilter),
    )
    search_fields = ("id", "sucursal__nombre", "usuario__email",
                     "usuario__first_name", "usuario__last_name")
    ordering = ("-abierto_en", "-creado_en")
    readonly_fields = (
        "empresa",
        "sucursal",
        "usuario",
        "cerrado_por",
        "abierto_en",
        "cerrado_en",
        "creado_en",
        "actualizado_en",
        "estado_badge",
    )
    fields = (
        "empresa",
        "sucursal",
        "usuario",
        "abierto_en",
        "cerrado_por",
        "cerrado_en",
        "estado_badge",
        "notas",
        "creado_en",
        "actualizado_en",
    )
    inlines = [CierreCajaTotalInline]
    actions = ["delete_selected"]
    # --- decoradores / helpers visuales ---

    def abierto_en_local(self, obj: CierreCaja):
        return localtime(obj.abierto_en).strftime("%Y-%m-%d %H:%M")
    abierto_en_local.short_description = "Abierto en"

    def cerrado_en_local(self, obj: CierreCaja):
        return "—" if obj.cerrado_en is None else localtime(obj.cerrado_en).strftime("%Y-%m-%d %H:%M")
    cerrado_en_local.short_description = "Cerrado en"

    def estado_badge(self, obj: CierreCaja):
        if obj.cerrado_en is None:
            return format_html('<span style="padding:2px 6px;border-radius:8px;background:#fde68a;color:#7c2d12;">ABIERTO</span>')
        return format_html('<span style="padding:2px 6px;border-radius:8px;background:#dcfce7;color:#14532d;">CERRADO</span>')
    estado_badge.short_description = "Estado"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # permitir borrar solo a superusuarios
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_delete_permission(request):
            actions.pop("delete_selected", None)
        return actions


@admin.register(CierreCajaTotal)
class CierreCajaTotalAdmin(admin.ModelAdmin):
    list_display = ("cierre", "medio", "monto",
                    "propinas", "total_incl_propina")
    list_filter = ("medio", "cierre__empresa", "cierre__sucursal")
    search_fields = ("cierre__id", "medio__nombre")
    readonly_fields = ("cierre", "medio", "monto", "propinas")
    ordering = ("-creado_en",)  # ahora sí existe en DB
    date_hierarchy = "creado_en"
    list_select_related = ("cierre", "medio")

    actions = ["delete_selected"]

    def total_incl_propina(self, obj: CierreCajaTotal):
        return (obj.monto or Decimal("0")) + (obj.propinas or Decimal("0"))
    total_incl_propina.short_description = "Total (incl. propina)"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Solo superuser puede borrar (p. ej., limpieza en dev)
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_delete_permission(request):
            actions.pop("delete_selected", None)
        return actions


# apps/cashbox/admin.py


@admin.register(TurnoCaja)
class TurnoCajaAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "sucursal", "abierto_en",
                    "cerrado_en", "abierto_por", "cerrado_por", "monto_contado_total")
    list_filter = ("empresa", "sucursal", "abierto_en", "cerrado_en")
    search_fields = ("responsable_nombre", "observaciones")
    date_hierarchy = "abierto_en"


@admin.register(TurnoCajaTotal)
class TurnoCajaTotalAdmin(admin.ModelAdmin):
    list_display = ("id", "turno", "medio_nombre",
                    "monto_teorico", "monto_contado", "dif_monto")
    list_filter = ("turno__empresa", "turno__sucursal")
    search_fields = ("medio_nombre",)
