# apps/org/services/empresa.py

from typing import Optional
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.saas.limits import can_create_empresa
from apps.saas.services.subscriptions import ensure_default_subscription_for_empresa

from ..models import Empresa, EmpresaConfig

User = get_user_model()


class PlanLimitError(PermissionError):
    """Se lanza cuando SAAS_ENFORCE_LIMITS=True y el plan bloquea la acción."""


def crear_empresa(nombre: str, subdominio: str, user: User, logo=None) -> Empresa:
    """
    Crea una empresa y asigna al usuario como admin (la membresía se resuelve afuera).
    - Valida límites del plan con can_create_empresa(user).
    - Crea suscripción default (trial si corresponde).
    """
    gate = can_create_empresa(user)
    if gate.should_block() and getattr(settings, "SAAS_ENFORCE_LIMITS", False):
        raise PlanLimitError(
            gate.message or "Tu plan no permite crear más empresas.")

    empresa = Empresa.objects.create(
        nombre=nombre, subdominio=subdominio, logo=logo)

    # Configuración inicial por defecto (ejemplo)
    EmpresaConfig.objects.create(
        empresa=empresa, clave="moneda", valor={"simbolo": "$"})

    # Suscripción default (trial si corresponde). No bloqueamos si falla en MVP.
    try:
        ensure_default_subscription_for_empresa(empresa=empresa)
    except Exception:
        pass

    return empresa


def actualizar_empresa(empresa: Empresa, **datos) -> Empresa:
    """Actualiza los datos de la empresa."""
    for field, value in datos.items():
        setattr(empresa, field, value)
    empresa.save()
    return empresa
