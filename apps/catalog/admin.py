# apps/catalog/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Servicio


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    """
    Admin de soporte para el catálogo de servicios.
    Pensado para tareas de operación/soporte: activar/desactivar, correcciones puntuales, etc.
    """
    list_display = (
        "nombre",
        "empresa",
        "slug",
        "estado_badge",
        "actualizado",
    )
    list_select_related = ("empresa",)
    list_filter = ("empresa", "activo")
    search_fields = (
        "nombre",
        "slug",
        "descripcion",
    )
    ordering = ("empresa", "nombre", "id")
    date_hierarchy = "creado"
    list_per_page = 50

    # Si tenés EmpresaAdmin con search_fields, esto habilita el widget de autocompletado
    autocomplete_fields = ["empresa"]

    # Permite editar el flag activo desde el listado
    list_editable = ()

    # Prepopular slug desde nombre (solo a nivel admin)
    prepopulated_fields = {"slug": ("nombre",)}

    fieldsets = (
        (_("Datos básicos"), {
            "fields": ("empresa", "nombre", "slug", "descripcion", "activo"),
        }),
        (_("Trazabilidad"), {
            "fields": ("creado", "actualizado"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("creado", "actualizado")

    def estado_badge(self, obj: Servicio):
        color = "28a745" if obj.activo else "6c757d"
        label = _("Activo") if obj.activo else _("Inactivo")
        # Usamos un span simple para evitar dependencias de CSS del admin
        return format_html(
            '<span style="display:inline-block;padding:.2rem .45rem;border-radius:.25rem;'
            'font-size:.75rem;color:#fff;background-color:#{};">{}</span>',
            color, label
        )

    estado_badge.short_description = _("Estado")
    estado_badge.admin_order_field = "activo"

    # --------
    # Acciones
    # --------
    actions = ("accion_activar", "accion_desactivar")

    @admin.action(description=_("Marcar seleccionados como activos"))
    def accion_activar(self, request, queryset):
        updated = queryset.update(activo=True)
        self.message_user(request, _(
            "%(count)d servicio(s) activado(s).") % {"count": updated})

    @admin.action(description=_("Marcar seleccionados como inactivos"))
    def accion_desactivar(self, request, queryset):
        updated = queryset.update(activo=False)
        self.message_user(request, _(
            "%(count)d servicio(s) desactivado(s).") % {"count": updated})
