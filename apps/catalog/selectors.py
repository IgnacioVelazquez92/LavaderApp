# apps/catalog/selectors.py
from __future__ import annotations

from typing import Optional, Iterable

from django.db.models import QuerySet
from django.db.models.functions import Lower

from apps.catalog.models import Servicio
from apps.org.models import Empresa


# ==============
# Query Builders
# ==============

def servicios_de_empresa(empresa: Empresa) -> QuerySet[Servicio]:
    """
    Retorna todos los servicios scopeados a la empresa.
    Orden por nombre (case-insensitive), luego id.
    """
    return (
        Servicio.objects
        .para_empresa(empresa)
        .order_by(Lower("nombre"), "id")
    )


def servicios_activos(empresa: Empresa) -> QuerySet[Servicio]:
    """
    Servicios activos dentro de la empresa.
    Ideal para combos/selects en UI o pricing.
    """
    return (
        Servicio.objects
        .para_empresa(empresa)
        .activos()
        .order_by(Lower("nombre"), "id")
    )


def buscar_servicios(empresa: Empresa, q: Optional[str]) -> QuerySet[Servicio]:
    """
    Búsqueda simple por nombre (icontains, case-insensitive) en el scope de empresa.
    Si `q` es vacío/None, retorna todos los servicios de la empresa.
    """
    base = Servicio.objects.para_empresa(empresa)
    q = (q or "").strip()
    if not q:
        return base.order_by(Lower("nombre"), "id")
    return base.filter(nombre__icontains=q).order_by(Lower("nombre"), "id")


# ==================
# Single-object gets
# ==================

def get_servicio_por_id(empresa: Empresa, servicio_id: int) -> Optional[Servicio]:
    """
    Obtiene un servicio por pk asegurando pertenencia a la empresa.
    Retorna None si no existe o no pertenece.
    """
    try:
        return Servicio.objects.get(pk=servicio_id, empresa=empresa)
    except Servicio.DoesNotExist:
        return None


def get_servicio_por_slug(empresa: Empresa, slug: str) -> Optional[Servicio]:
    """
    Obtiene un servicio por slug dentro del scope de empresa.
    Retorna None si no existe.
    """
    slug = (slug or "").strip()
    if not slug:
        return None
    try:
        return Servicio.objects.get(empresa=empresa, slug=slug)
    except Servicio.DoesNotExist:
        return None


# =======================
# Checks / utilidades CI
# =======================

def existe_nombre_en_empresa(
    empresa: Empresa,
    nombre: str,
    exclude_pk: Optional[int] = None,
) -> bool:
    """
    Verifica si ya existe un servicio con `nombre` (case-insensitive) en la empresa.
    Útil para validaciones en forms o servicios.
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return False
    qs = (
        Servicio.objects
        .para_empresa(empresa)
        .annotate(nombre_ci=Lower("nombre"))
        .filter(nombre_ci=nombre.lower())
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()
