# apps/saas/services/plans.py
"""
Servicios de Planes SaaS.

Incluye:
- Alta/edición de Plan.
- Marcar/desmarcar Plan por defecto (asegura unicidad lógica del default activo).
- Helpers utilitarios para tests/seed.

*No* hace validaciones de pasarela; solo negocio interno.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction

from ..models import PlanSaaS
from . import ServiceError, ServiceResult

logger = logging.getLogger(__name__)


@transaction.atomic
def create_plan(*, nombre: str, descripcion: str = "", activo: bool = True,
                default: bool = False, trial_days: int = 0,
                max_empresas_por_usuario: int = 1,
                max_sucursales_por_empresa: int = 1,
                max_usuarios_por_empresa: int = 5,
                max_empleados_por_sucursal: int = 5,
                max_storage_mb: int = 200,
                precio_mensual: float = 0.0,
                external_plan_id: str = "") -> ServiceResult:
    """
    Crea un plan SaaS.

    Garantías:
    - Si default=True y activo, desmarca otros default activos (unicidad lógica).

    Returns:
        ServiceResult(ok, message, data={"plan": plan})
    """
    if trial_days < 0:
        raise ServiceError("trial_days no puede ser negativo.")
    plan = PlanSaaS.objects.create(
        nombre=nombre,
        descripcion=descripcion,
        activo=activo,
        default=default,
        trial_days=trial_days,
        max_empresas_por_usuario=max_empresas_por_usuario,
        max_sucursales_por_empresa=max_sucursales_por_empresa,
        max_usuarios_por_empresa=max_usuarios_por_empresa,
        max_empleados_por_sucursal=max_empleados_por_sucursal,
        max_storage_mb=max_storage_mb,
        precio_mensual=precio_mensual,
        external_plan_id=external_plan_id,
    )
    if plan.default and plan.activo:
        _ensure_single_active_default(keep_id=plan.id)
    logger.info("Plan creado: %s (default=%s activo=%s)",
                plan.nombre, plan.default, plan.activo)
    return ServiceResult(ok=True, data={"plan": plan})


@transaction.atomic
def update_plan(*, plan: PlanSaaS, **attrs) -> ServiceResult:
    """
    Edita atributos del plan. Si se pasa default=True y activo=True,
    asegura unicidad del default activo.

    Atributos admitidos: descripcion, activo, default, trial_days, límites, precio_mensual, external_plan_id.
    """
    allowed = {
        "descripcion", "activo", "default", "trial_days",
        "max_empresas_por_usuario", "max_sucursales_por_empresa",
        "max_usuarios_por_empresa", "max_empleados_por_sucursal",
        "max_storage_mb", "precio_mensual", "external_plan_id",
        "nombre",
    }
    for k, v in list(attrs.items()):
        if k not in allowed:
            attrs.pop(k)
    for k, v in attrs.items():
        setattr(plan, k, v)
    plan.save(update_fields=list(attrs.keys()))

    if plan.default and plan.activo:
        _ensure_single_active_default(keep_id=plan.id)

    logger.info("Plan actualizado: %s (default=%s activo=%s)",
                plan.nombre, plan.default, plan.activo)
    return ServiceResult(ok=True, data={"plan": plan})


@transaction.atomic
def set_default_plan(*, plan: PlanSaaS) -> ServiceResult:
    """
    Marca un plan como default y activo; desmarca otros default activos.
    """
    plan.default = True
    plan.activo = True
    plan.save(update_fields=["default", "activo"])
    _ensure_single_active_default(keep_id=plan.id)
    logger.info("Plan marcado como default: %s", plan.nombre)
    return ServiceResult(ok=True, data={"plan": plan})


def _ensure_single_active_default(*, keep_id) -> None:
    """
    Garantiza que solo haya un plan activo marcado como default.
    """
    (PlanSaaS.objects
     .filter(default=True, activo=True)
     .exclude(id=keep_id)
     .update(default=False))
