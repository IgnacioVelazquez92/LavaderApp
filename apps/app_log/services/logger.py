# apps/app_log/services/logger.py
"""
Servicio central de logging a base de datos.

Funciones principales:
- log_event: registrar un evento técnico o de negocio.
- log_exception: registrar una excepción con traceback.
- log_errors: decorador para envolver funciones y capturar errores.

Incluye sanitización de metadata para evitar volcar
contraseñas, tokens o headers sensibles.
"""

from __future__ import annotations
from functools import wraps
from typing import Any, Dict, Optional
from django.http import HttpRequest
from django.utils.timezone import now
from ..models import AppLog
from ..utils import get_current_request

# Claves que no deben guardarse sin redacción
SAFE_REDACT_KEYS = [
    "password", "token", "authorization",
    "cookie", "secret", "apikey", "api_key"
]


def _sanitize_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redacta valores sensibles (contraseñas, tokens).
    """
    redacted = {}
    for k, v in (meta or {}).items():
        key = str(k).lower()
        if any(s in key for s in SAFE_REDACT_KEYS):
            redacted[k] = "***redacted***"
        else:
            redacted[k] = v
    return redacted


def _request_context(request: Optional[HttpRequest]) -> Dict[str, Any]:
    """
    Construye un diccionario con el contexto básico del request:
    - path, método, IP, user-agent, request_id
    - usuario autenticado (id, username)
    - empresa/sucursal activa (según TenancyMiddleware)
    """
    if request is None:
        request = get_current_request()
    if not request:
        return {}

    user = getattr(request, "user", None)
    ctx = {
        "path": getattr(request, "path", None),
        "method": getattr(request, "method", None),
        "ip": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT"),
        "request_id": str(getattr(request, "request_id", "")) or None,
    }
    if getattr(user, "is_authenticated", False):
        ctx["user_id"] = getattr(user, "id", None)
        ctx["username"] = getattr(user, "username", None)

    # Compat con TenancyMiddleware
    ctx["empresa_id"] = (
        getattr(getattr(request, "empresa_activa", None), "id", None)
        or getattr(request, "empresa_activa", None)
    )
    ctx["sucursal_id"] = (
        getattr(getattr(request, "sucursal_activa", None), "id", None)
        or getattr(request, "sucursal_activa", None)
    )
    return ctx


def log_event(
    nivel: str,
    origen: str,
    evento: str,
    mensaje: str,
    meta: Optional[Dict[str, Any]] = None,
    *,
    request: Optional[HttpRequest] = None,
    empresa_id: Optional[str] = None,
) -> str:
    """
    Crea un registro AppLog en base de datos.

    Args:
        nivel: debug|info|warning|error|critical
        origen: módulo/origen del evento (ej. "http", "sales.services")
        evento: etiqueta corta del evento (ej. "access_log")
        mensaje: mensaje breve
        meta: diccionario adicional (se sanitiza)
        request: opcional, para contexto automático
        empresa_id: opcional, para override manual

    Returns:
        id del log creado (str)
    """
    ctx = _request_context(request)
    if empresa_id is None:
        empresa_id = ctx.get("empresa_id")
    rid = ctx.get("request_id")

    meta_total = _sanitize_meta({**ctx, **(meta or {})})
    obj = AppLog.objects.create(
        nivel=nivel,
        origen=origen[:120],
        evento=evento[:80],
        mensaje=mensaje,
        meta_json=meta_total,
        empresa_id=empresa_id,
        user_id=meta_total.get("user_id"),
        username=meta_total.get("username"),
        request_id=rid,
        http_method=meta_total.get("method"),
        http_path=meta_total.get("path"),
        http_status=meta_total.get("status"),
        duration_ms=meta_total.get("duration_ms"),
        ip=meta_total.get("ip"),
        user_agent=meta_total.get("user_agent"),
        creado_en=now(),
    )
    return str(obj.id)


def log_exception(
    origen: str,
    evento: str,
    exc: Exception,
    *,
    request: Optional[HttpRequest] = None,
    empresa_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Captura una excepción y la guarda en AppLog.

    Args:
        origen: módulo que produce la excepción
        evento: etiqueta corta
        exc: excepción capturada
        request: opcional, para contexto
        empresa_id: opcional
        extra: metadata extra
    """
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    meta = {"exception_type": type(exc).__name__, "traceback": tb}
    if extra:
        meta.update(extra)
    return log_event(
        "error",
        origen,
        evento,
        mensaje=str(exc),
        meta=meta,
        request=request,
        empresa_id=empresa_id,
    )


# -------------------------------------------------------------------
# Decorador práctico para envolver funciones con logging de errores
# -------------------------------------------------------------------


def log_errors(origen: str, evento: str):
    """
    Decorador para capturar excepciones de funciones y registrarlas.
    """
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                log_exception(origen, evento, e, request=request)
                raise
        return wrapper
    return deco
