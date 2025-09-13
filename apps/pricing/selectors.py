# apps/pricing/selectors.py
from __future__ import annotations

from django.utils import timezone
from django.db.models import QuerySet

from .models import PrecioServicio


def listar_precios(empresa, *, sucursal=None, servicio=None, tipo=None, vigentes_en=None, activos=None) -> QuerySet[PrecioServicio]:
    """
    Devuelve un queryset filtrado por los parámetros opcionales.
    - vigentes_en: date → devuelve solo precios activos vigentes ese día.
    - activos: bool|None → filtra por flag 'activo'.
    """
    qs = PrecioServicio.objects.de_empresa(empresa).select_related(
        "empresa", "sucursal", "servicio", "tipo_vehiculo"
    )
    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)
    if servicio is not None:
        qs = qs.filter(servicio=servicio)
    if tipo is not None:
        qs = qs.filter(tipo_vehiculo=tipo)
    if vigentes_en:
        qs = qs.vigentes_en(vigentes_en)
    if activos is True:
        qs = qs.filter(activo=True)
    elif activos is False:
        qs = qs.filter(activo=False)
    return qs.order_by("-vigencia_inicio", "-actualizado")
