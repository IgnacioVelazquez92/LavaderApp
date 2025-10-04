# apps/notifications/selectors.py
"""
Consultas (lecturas) para notificaciones.
Mantener SELECTs comunes encapsulados y reutilizables en vistas/services.
"""

from __future__ import annotations
from .models import EmailServer
from .models import PlantillaNotif

from datetime import datetime
from typing import Iterable

from django.db.models import QuerySet

from .models import PlantillaNotif, LogNotif, Canal


def plantillas_activas(empresa_id: int, canal: str | None = None) -> QuerySet[PlantillaNotif]:
    qs = PlantillaNotif.objects.filter(empresa_id=empresa_id, activo=True)
    if canal:
        qs = qs.filter(canal=canal)
    return qs.order_by("clave")


def logs_por_venta(venta_id) -> QuerySet[LogNotif]:
    return LogNotif.objects.filter(venta_id=venta_id).order_by("-enviado_en")


def logs_por_rango(
    empresa_id: int,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    canal: str | None = None,
    estados: Iterable[str] | None = None,
) -> QuerySet[LogNotif]:
    qs = LogNotif.objects.filter(empresa_id=empresa_id)
    if canal:
        qs = qs.filter(canal=canal)
    if estados:
        qs = qs.filter(estado__in=list(estados))
    if desde:
        qs = qs.filter(enviado_en__gte=desde)
    if hasta:
        qs = qs.filter(enviado_en__lt=hasta)
    return qs.order_by("-enviado_en")


def plantillas_activas_whatsapp(empresa_id):
    return (PlantillaNotif.objects
            .filter(empresa_id=empresa_id, activo=True, canal=Canal.WHATSAPP)
            .order_by("clave"))


def get_smtp_activo(empresa) -> EmailServer | None:
    """Devuelve el EmailServer ACTIVO más reciente para la empresa."""
    if not empresa:
        return None
    return (
        EmailServer.objects
        .filter(empresa=empresa, activo=True)
        .order_by("-updated_at")
        .first()
    )


def has_smtp_activo(empresa) -> bool:
    """True si existe al menos un SMTP activo para la empresa."""
    return get_smtp_activo(empresa) is not None
