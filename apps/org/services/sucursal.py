# apps/org/services/sucursal.py

from typing import Optional
from django.conf import settings

from apps.saas.limits import can_create_sucursal

from ..models import Sucursal, Empresa


class PlanLimitError(PermissionError):
    """Se lanza cuando SAAS_ENFORCE_LIMITS=True y el plan bloquea la acción."""


def crear_sucursal(
    empresa: Empresa,
    nombre: str,
    direccion: str = "",
    codigo_interno: Optional[str] = None,
) -> Sucursal:
    """
    Crea una sucursal para la empresa.
    - Valida límites del plan con can_create_sucursal(empresa).
    - Si no se provee codigo_interno, el modelo lo autogenera en save().
    """
    gate = can_create_sucursal(empresa)
    if gate.should_block() and getattr(settings, "SAAS_ENFORCE_LIMITS", False):
        raise PlanLimitError(
            gate.message or "Tu plan no permite crear más sucursales.")

    sucursal = Sucursal.objects.create(
        empresa=empresa,
        nombre=nombre,
        direccion=direccion,
        # dejar que el modelo lo genere si está vacío
        codigo_interno=codigo_interno or "",
    )
    return sucursal


def actualizar_sucursal(sucursal: Sucursal, **datos) -> Sucursal:
    for field, value in datos.items():
        setattr(sucursal, field, value)
    sucursal.save()
    return sucursal
