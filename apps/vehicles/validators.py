"""
validators.py — Validadores y utilidades de patente para apps/vehicles

Incluye:
- normalizar_patente: estandariza la patente (sin guiones/espacios, MAYÚSCULAS).
- validate_patente_format: valida formato AR (AAA123 o AA123AA).
- ensure_patente_unique_in_company: chequea unicidad por empresa (típicamente desde el Form).
"""

import re
from typing import Optional
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Patrones de patente Argentina:
# - Viejo: ABC123  (3 letras + 3 dígitos)
# - Nuevo: AB123CD (2 letras + 3 dígitos + 2 letras)
_RE_VIEJO = re.compile(r"^[A-Z]{3}[0-9]{3}$")
_RE_NUEVO = re.compile(r"^[A-Z]{2}[0-9]{3}[A-Z]{2}$")


def normalizar_patente(value: str) -> str:
    """
    Estandariza la patente removiendo espacios y guiones y forzando MAYÚSCULAS.
    Ej.: 'ab 123 cd' -> 'AB123CD', 'abc-123' -> 'ABC123'
    """
    if not value:
        return value
    return value.replace("-", "").replace(" ", "").upper()


def validate_patente_format(value: str) -> None:
    """
    Valida que 'value' (ya normalizado o no) cumpla uno de los formatos AR vigentes.
    Lanza ValidationError si no coincide.
    """
    v = normalizar_patente(value or "")
    if not v or not (_RE_VIEJO.match(v) or _RE_NUEVO.match(v)):
        raise ValidationError(
            _(
                "Formato de patente inválido. Usá 'ABC123' o 'AB123CD' "
                "(se aceptan variantes con espacio/guión, se normalizan)."
            )
        )


def ensure_patente_unique_in_company(*, empresa, patente: str, exclude_pk: Optional[int] = None, only_active: bool = True) -> None:
    """
    Chequea que la patente NO exista en la misma empresa.
    - empresa: instancia de org.Empresa
    - patente: string (se normaliza adentro)
    - exclude_pk: ignora este PK (útil en edición)
    - only_active: True => considera solo Vehiculos activos (respeta soft delete)

    Lanza ValidationError si hay colisión.
    """
    from .models import Vehiculo  # import diferido para evitar ciclos

    norm = normalizar_patente(patente or "")
    qs = Vehiculo.objects.filter(empresa=empresa, patente=norm)
    if only_active:
        qs = qs.filter(activo=True)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError(
            _("Ya existe un vehículo con esta patente en tu empresa.")
        )
