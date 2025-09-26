# apps/saas/admin.py
"""
Admin de Django para PlanSaaS y SuscripcionSaaS.

Objetivo:
- Gestión interna de planes y suscripciones (sin pasarela en MVP).
- Vistas claras de estado, vigencia y límites para soporte.

Sugerencia:
- Restringir acceso a superuser / staff autorizado.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import PlanSaaS, SuscripcionSaaS


@admin.register(PlanSaaS)
class PlanSaaSAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "precio_mensual",
        "default",
        "activo",
        "max_empresas_por_usuario",
        "max_sucursales_por_empresa",
        "max_usuarios_por_empresa",
        "max_empleados_por_sucursal",
    )
    list_filter = ("activo", "default")
    search_fields = ("nombre", "descripcion", "external_plan_id")
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        (None, {
            "fields": ("nombre", "descripcion", "activo", "default"),
        }),
        ("Trial", {
            "fields": ("trial_days",),
        }),
        ("Límites (soft)", {
            "fields": (
                "max_empresas_por_usuario",
                "max_sucursales_por_empresa",
                "max_usuarios_por_empresa",
                "max_empleados_por_sucursal",
                "max_storage_mb",
            ),
        }),
        ("Comercial", {
            "fields": ("precio_mensual", "external_plan_id"),
        }),
        ("Auditoría", {
            "fields": ("creado_en", "actualizado_en"),
        }),
    )


@admin.register(SuscripcionSaaS)
class SuscripcionSaaSAdmin(admin.ModelAdmin):
    list_display = (
        "empresa",
        "plan",
        "estado",
        "payment_status",
        "inicio",
        "fin",
        "vigente_badge",
        "last_payment_at",
        "next_billing_at",
    )
    list_filter = ("estado", "payment_status", "plan")
    search_fields = (
        "empresa__nombre",
        "external_customer_id",
        "external_subscription_id",
        "external_plan_id",
    )
    autocomplete_fields = ("empresa", "plan")
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        (None, {
            "fields": ("empresa", "plan"),
        }),
        ("Estado funcional", {
            "fields": ("estado", "inicio", "fin"),
        }),
        ("Pago / Pasarela", {
            "fields": (
                "payment_status",
                "external_customer_id",
                "external_subscription_id",
                "external_plan_id",
                "last_payment_at",
                "next_billing_at",
            ),
        }),
        ("Auditoría", {
            "fields": ("creado_en", "actualizado_en"),
        }),
    )

    @admin.display(description="Vigente", boolean=False)
    def vigente_badge(self, obj: SuscripcionSaaS) -> str:
        color = "#16a34a" if obj.vigente else "#ef4444"
        text = "Sí" if obj.vigente else "No"
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
            'background:{0};color:white;font-weight:600;">{1}</span>',
            color, text
        )
