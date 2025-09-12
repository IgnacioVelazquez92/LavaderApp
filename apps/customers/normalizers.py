import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def clean_email(value: str | None) -> str | None:
    """Normaliza email a lower-case y valida formato."""
    if not value:
        return ""
    email = value.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise
    return email


def clean_documento(value: str | None) -> str | None:
    """Quita separadores y espacios del documento."""
    if not value:
        return ""
    return re.sub(r"\D+", "", value.strip())


def clean_tel_e164(value: str | None) -> str | None:
    """
    Normaliza teléfono al estilo E.164 (+ prefijo).
    Este MVP asume que viene ya con +54... o similar.
    En el futuro se puede mejorar para detectar 15/0 al inicio.
    """
    if not value:
        return ""
    tel = value.strip().replace(" ", "").replace("-", "")
    # Asegurar que empiece con '+'
    if not tel.startswith("+"):
        # Asumimos Argentina +54 por defecto
        if tel.startswith("0"):
            tel = tel[1:]
        tel = "+54" + tel
    return tel


def strip_tel(value: str | None) -> str:
    """Versión sin símbolos del teléfono, útil para búsquedas laxas."""
    if not value:
        return ""
    return re.sub(r"\D+", "", value)


def capitalizar(value: str | None) -> str:
    """Capitaliza nombre/apellido/razón social."""
    if not value:
        return ""
    return value.strip().title()
