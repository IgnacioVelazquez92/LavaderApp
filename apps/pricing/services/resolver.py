# apps/pricing/services/resolver.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from django.utils import timezone

from ..models import PrecioServicio


class PrecioNoDisponibleError(Exception):
    """No hay precio vigente para la combinación solicitada."""
    pass


@dataclass(frozen=True)
class PrecioResult:
    """DTO liviano para exponer solo lo necesario a 'sales'."""
    precio_id: int
    precio: str          # mantener como str para no perder precisión Decimal al serializar
    moneda: str
    vigente_desde: str
    vigente_hasta: Optional[str]


def get_precio_vigente(*, empresa, sucursal, servicio, tipo_vehiculo, fecha=None) -> PrecioServicio:
    """
    Devuelve el objeto PrecioServicio vigente (activo) para la combinación dada en 'fecha' (hoy por defecto).

    Selección:
      - Dentro del rango de vigencia.
      - Activo=True.
      - Si hay múltiples candidatos, el de 'vigencia_inicio' más reciente.
    """
    if fecha is None:
        fecha = timezone.localdate()

    qs = (
        PrecioServicio.objects
        .de_empresa(empresa)
        .de_combinacion(sucursal, servicio, tipo_vehiculo)
        .vigentes_en(fecha)
        .order_by("-vigencia_inicio", "-actualizado")
    )
    obj = qs.first()
    if not obj:
        raise PrecioNoDisponibleError(
            "No existe un precio vigente para la combinación Servicio × Tipo de Vehículo × Sucursal en la fecha solicitada."
        )
    return obj


def get_precio_vigente_dto(*, empresa, sucursal, servicio, tipo_vehiculo, fecha=None) -> PrecioResult:
    """
    Variante que devuelve un DTO serializable y estable para otras capas (e.g., 'sales').
    """
    obj = get_precio_vigente(
        empresa=empresa, sucursal=sucursal, servicio=servicio, tipo_vehiculo=tipo_vehiculo, fecha=fecha
    )
    return PrecioResult(
        precio_id=obj.id,
        precio=str(obj.precio),
        moneda=obj.moneda,
        vigente_desde=obj.vigencia_inicio.isoformat(),
        vigente_hasta=obj.vigencia_fin.isoformat() if obj.vigencia_fin else None,
    )
