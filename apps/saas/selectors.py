# apps/saas/selectors.py
"""
Selectores (lecturas puras) para el módulo SaaS.

Responsabilidades:
- Obtener planes activos y el plan por defecto.
- Resolver la suscripción vigente de una empresa.
- Exponer snapshots ligeros de uso (para paneles/UX).

Importante:
- Aquí NO hay efectos secundarios (no writes).
- La lógica de "enforcement" de límites NO va acá (ver limits.py).
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from django.db.models import QuerySet
from django.utils import timezone

from .models import PlanSaaS, SuscripcionSaaS


# ---------------------------
# Planes
# ---------------------------

def planes_activos() -> QuerySet[PlanSaaS]:
    """
    Devuelve los planes activos ordenados por precio (ascendente).
    Útil para listados/admin interno.
    """
    return PlanSaaS.objects.filter(activo=True).order_by("precio_mensual", "nombre")


def plan_default() -> Optional[PlanSaaS]:
    """
    Devuelve el plan por defecto (si hay varios marcados, prioriza el más barato activo).
    Retorna None si no hay ninguno.
    """
    qs = PlanSaaS.objects.filter(activo=True, default=True).order_by(
        "precio_mensual", "nombre")
    return qs.first()


# ---------------------------
# Suscripciones
# ---------------------------

def suscripcion_de(empresa) -> Optional[SuscripcionSaaS]:
    """
    Devuelve la suscripción asociada a la empresa (puede no existir en entornos legacy).
    """
    return getattr(empresa, "suscripcion", None)


def suscripcion_vigente_de(empresa) -> Optional[SuscripcionSaaS]:
    """
    Devuelve la suscripción vigente (estado y fechas).
    """
    sub = suscripcion_de(empresa)
    if sub and sub.vigente:
        return sub
    return None


def mi_suscripcion(empresa) -> Optional[SuscripcionSaaS]:
    """
    Alias semántico para plantillas/vistas.
    """
    return suscripcion_de(empresa)


# ---------------------------
# Snapshots ligeros para panel
# ---------------------------

def suscripcion_snapshot(empresa) -> Dict[str, Any]:
    """
    Estructura simple para alimentar el panel SaaS de la empresa.
    No calcula uso; solo empaqueta datos de plan/estado.
    """
    sub = suscripcion_de(empresa)
    if not sub:
        return {
            "has_subscription": False,
            "plan": None,
            "estado": None,
            "vigente": False,
            "payment_status": None,
            "inicio": None,
            "fin": None,
            "trial_ends_at": None,
            "today": timezone.localdate(),
        }
    plan = sub.plan
    return {
        "has_subscription": True,
        "plan": {
            "id": str(plan.id),
            "nombre": plan.nombre,
            "precio_mensual": plan.precio_mensual,
            "trial_days": plan.trial_days,
            "limits": {
                "max_empresas_por_usuario": plan.max_empresas_por_usuario,
                "max_sucursales_por_empresa": plan.max_sucursales_por_empresa,
                "max_usuarios_por_empresa": plan.max_usuarios_por_empresa,
                "max_empleados_por_sucursal": plan.max_empleados_por_sucursal,
                "max_storage_mb": plan.max_storage_mb,
            },
        },
        "estado": sub.estado,
        "vigente": sub.vigente,
        "payment_status": sub.payment_status,
        "inicio": sub.inicio,
        "fin": sub.fin,
        "trial_ends_at": sub.trial_ends_at,
        "today": timezone.localdate(),
    }
