# apps/saas/services/__init__.py
"""
Servicios (casos de uso) del módulo SaaS.

Filosofía:
- Orquestan flujos de negocio (crear/editar plan, alta/cambio de suscripción, trial, pagos).
- No hacen rendering ni devuelven respuestas HTTP.
- Deben ser idempotentes en lo posible y registrar logging mínimo para auditoría liviana.
"""

from __future__ import annotations

from dataclasses import dataclass


class ServiceError(Exception):
    """Error controlado de capa de servicios (negocio)."""


@dataclass(frozen=True)
class ServiceResult:
    """Contenedor de resultado simple para estandarizar retornos en services."""
    ok: bool
    message: str | None = None
    data: dict | None = None
