# apps/saas/limits.py
"""
Chequeos de límites (gating) para el módulo SaaS.

Filosofía:
- Este módulo NO persiste nada. Solo calcula uso y decide si permitir/bloquear.
- El modo de aplicación se controla por setting:
    SAAS_ENFORCE_LIMITS = False  # MVP (avisos)
  Si se pone True, las funciones `can_*` deben interpretarse como BLOQUEO.

Coberturas:
- L1: Máx. empresas por usuario (owner).
- L2: Máx. sucursales por empresa.
- L3: Máx. empleados por sucursal (membresías activas asignadas a esa sucursal).
- (Opcional) Máx. usuarios por empresa (membresías activas en la empresa).

Integraciones esperadas:
- Org.SucursalCreateView → can_create_sucursal(empresa)
- Org.EmpleadoCreateView → can_add_empleado(sucursal)
- Onboarding Empresa → can_create_empresa(user)

Notas:
- El "plan" relevante para L1 (crear empresa) proviene del plan por defecto vigente
  (o política global). En MVP, tomamos el plan default activo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any

from django.conf import settings

from apps.accounts.models import EmpresaMembership  # membership de usuario↔empresa
from apps.org.models import Sucursal, Empresa
from .selectors import plan_default, suscripcion_de


# ---------------------------
# Configuración
# ---------------------------

def enforce_limits() -> bool:
    """
    Flag global para decidir si los límites son HARD (bloqueo) o SOFT (warning).
    """
    return bool(getattr(settings, "SAAS_ENFORCE_LIMITS", False))


# ---------------------------
# Contadores de uso
# ---------------------------

def count_empresas_owner(user) -> int:
    """
    Empresas donde el usuario es owner y la membresía está activa.
    """
    return (
        EmpresaMembership.objects
        .filter(user=user, is_owner=True, activo=True)
        .values("empresa")
        .distinct()
        .count()
    )


def count_sucursales_empresa(empresa: Empresa) -> int:
    """
    Total de sucursales de una empresa.
    """
    return empresa.sucursales.count()


def count_memberships_empresa(empresa: Empresa) -> int:
    """
    Membresías activas de la empresa (usuarios en la empresa).
    """
    return EmpresaMembership.objects.filter(empresa=empresa, activo=True).count()


def count_empleados_en_sucursal(sucursal: Sucursal) -> int:
    """
    Membresías activas asignadas a una sucursal específica.
    """
    return EmpresaMembership.objects.filter(
        empresa=sucursal.empresa,
        sucursal_asignada=sucursal,
        activo=True,
    ).count()


# ---------------------------
# Snapshots de uso (para panel)
# ---------------------------

def get_usage_snapshot(empresa: Empresa, sucursal: Optional[Sucursal] = None) -> Dict[str, Any]:
    """
    Devuelve un snapshot de uso vs límites para armar el panel SaaS.
    - Toma los límites del plan de la suscripción de la empresa.
    - Si no hay suscripción/plan, devuelve límites = None (MVP: no bloquea).
    """
    sub = suscripcion_de(empresa)
    if not sub or not sub.plan:
        return {
            "plan": None,
            "empresa": empresa.id,
            "sucursales": {"used": count_sucursales_empresa(empresa), "limit": None},
            "usuarios_empresa": {"used": count_memberships_empresa(empresa), "limit": None},
            "empleados_sucursal": (
                {"used": count_empleados_en_sucursal(sucursal), "limit": None}
                if sucursal else None
            ),
            "storage_mb": {"used": 0, "limit": None},  # placeholder
        }

    plan = sub.plan
    data = {
        "plan": {
            "id": str(plan.id),
            "nombre": plan.nombre,
        },
        "empresa": empresa.id,
        "sucursales": {
            "used": count_sucursales_empresa(empresa),
            "limit": plan.max_sucursales_por_empresa,
        },
        "usuarios_empresa": {
            "used": count_memberships_empresa(empresa),
            "limit": plan.max_usuarios_por_empresa,
        },
        "storage_mb": {
            "used": 0,  # TODO: integrar cuando midamos uso real
            "limit": plan.max_storage_mb,
        },
    }
    if sucursal:
        data["empleados_sucursal"] = {
            "used": count_empleados_en_sucursal(sucursal),
            "limit": plan.max_empleados_por_sucursal,
        }
    return data


# ---------------------------
# Resultado estándar de can_*
# ---------------------------

@dataclass(frozen=True)
class GateResult:
    allowed: bool
    message: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None

    def should_block(self) -> bool:
        """
        True si corresponde BLOQUEAR la acción (cuando enforce_limits está ON y allowed es False).
        """
        return enforce_limits() and not self.allowed


# ---------------------------
# Reglas de gating
# ---------------------------

def can_create_empresa(user) -> GateResult:
    """
    L1. Máximo de empresas que un usuario puede crear/poseer (owner).
    Regla MVP: se usa el "plan por defecto" como política global.
    """
    plan = plan_default()
    if not plan:
        # Sin plan default → no bloqueamos/avisamos en MVP
        return GateResult(allowed=True)

    used = count_empresas_owner(user)
    limit_ = plan.max_empresas_por_usuario
    if used >= limit_:
        msg = (
            "Alcanzaste el máximo de empresas por usuario para tu plan actual. "
            "Contactá soporte o elegí un plan superior."
        )
        return GateResult(allowed=False, message=msg, usage={"used": used, "limit": limit_})
    return GateResult(allowed=True, usage={"used": used, "limit": limit_})


def can_create_sucursal(empresa: Empresa) -> GateResult:
    """
    L2. Máximo de sucursales por empresa según el plan de la empresa (suscripción).
    """
    sub = suscripcion_de(empresa)
    if not sub or not sub.plan:
        # Sin suscripción → MVP no bloquea (avisar opcionalmente)
        used = count_sucursales_empresa(empresa)
        return GateResult(
            allowed=True,
            message=None,
            usage={"used": used, "limit": None},
        )

    used = count_sucursales_empresa(empresa)
    limit_ = sub.plan.max_sucursales_por_empresa
    if used >= limit_:
        msg = "Alcanzaste el máximo de sucursales para tu plan. Considerá mejorar de plan."
        return GateResult(allowed=False, message=msg, usage={"used": used, "limit": limit_})
    return GateResult(allowed=True, usage={"used": used, "limit": limit_})


def can_add_empleado(sucursal: Sucursal) -> GateResult:
    """
    L3. Máximo de empleados por sucursal (membresías activas con esa sucursal asignada).
    Nota: si necesitás chequear además el límite de usuarios por empresa, hacelo en el servicio
    de alta de empleados combinando este check con `can_add_usuario_a_empresa`.
    """
    empresa = sucursal.empresa
    sub = suscripcion_de(empresa)
    used = count_empleados_en_sucursal(sucursal)

    if not sub or not sub.plan:
        return GateResult(allowed=True, usage={"used": used, "limit": None})

    limit_ = sub.plan.max_empleados_por_sucursal
    if used >= limit_:
        msg = "Alcanzaste el máximo de empleados por sucursal para tu plan."
        return GateResult(allowed=False, message=msg, usage={"used": used, "limit": limit_})
    return GateResult(allowed=True, usage={"used": used, "limit": limit_})


def can_add_usuario_a_empresa(empresa: Empresa) -> GateResult:
    """
    (Opcional) Límite de usuarios por empresa (membresías activas).
    Útil si querés mostrar aviso/bloqueo general al intentar invitar/crear empleados.
    """
    sub = suscripcion_de(empresa)
    used = count_memberships_empresa(empresa)

    if not sub or not sub.plan:
        return GateResult(allowed=True, usage={"used": used, "limit": None})

    limit_ = sub.plan.max_usuarios_por_empresa
    if used >= limit_:
        msg = "Alcanzaste el máximo de usuarios activos para tu plan."
        return GateResult(allowed=False, message=msg, usage={"used": used, "limit": limit_})
    return GateResult(allowed=True, usage={"used": used, "limit": limit_})
