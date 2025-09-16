# apps/app_log/selectors.py
"""
Consultas de lectura comunes para AppLog y AuditLog.
Mantener la lógica de filtrado fuera de las vistas facilita testeo y reutilización.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from django.db.models import QuerySet
from .models import AppLog, AuditLog


def list_access_logs(
    *,
    empresa_id: Optional[str] = None,
    nivel: Optional[str] = None,
    status: Optional[int] = None,
    path_icontains: Optional[str] = None,
    origen_icontains: Optional[str] = None,
    evento_icontains: Optional[str] = None,
    username_icontains: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = 1000,
) -> QuerySet[AppLog]:
    """
    Devuelve AppLog filtrado para análisis de tráfico/errores.
    """
    qs = AppLog.objects.all()
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    if nivel:
        qs = qs.filter(nivel=nivel)
    if status:
        qs = qs.filter(http_status=status)
    if path_icontains:
        qs = qs.filter(http_path__icontains=path_icontains)
    if origen_icontains:
        qs = qs.filter(origen__icontains=origen_icontains)
    if evento_icontains:
        qs = qs.filter(evento__icontains=evento_icontains)
    if username_icontains:
        qs = qs.filter(username__icontains=username_icontains)
    if desde:
        qs = qs.filter(creado_en__gte=desde)
    if hasta:
        qs = qs.filter(creado_en__lte=hasta)
    return qs[:limit]


def find_request_trace(request_id: str, *, limit: int = 1000) -> QuerySet[AppLog]:
    """
    Traza completa por request_id (access log + errores del mismo request).
    """
    return AppLog.objects.filter(request_id=request_id).order_by("-creado_en")[:limit]


def find_audit_for_resource(
    *,
    resource_type: str,
    resource_id: str,
    limit: int = 1000,
) -> QuerySet[AuditLog]:
    """
    Historial de auditoría para un recurso puntual (ej. sales.Venta:uuid).
    """
    return (
        AuditLog.objects.filter(
            resource_type=resource_type, resource_id=resource_id)
        .order_by("-creado_en")[:limit]
    )


def list_audit_logs(
    *,
    empresa_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    username_icontains: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    success: Optional[bool] = None,
    limit: int = 1000,
) -> QuerySet[AuditLog]:
    """
    Filtro general para auditoría de negocio (CRUD, login/logout).
    """
    qs = AuditLog.objects.all()
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    if resource_type:
        qs = qs.filter(resource_type=resource_type)
    if resource_id:
        qs = qs.filter(resource_id=resource_id)
    if action:
        qs = qs.filter(action=action)
    if username_icontains:
        qs = qs.filter(username__icontains=username_icontains)
    if success is not None:
        qs = qs.filter(success=success)
    if desde:
        qs = qs.filter(creado_en__gte=desde)
    if hasta:
        qs = qs.filter(creado_en__lte=hasta)
    return qs.order_by("-creado_en")[:limit]
