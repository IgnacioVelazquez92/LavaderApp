# apps/pricing/services/resolver.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from django.utils import timezone
from django.db.models import Q
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


def get_precio_vigente(empresa, sucursal, servicio, tipo_vehiculo, fecha: date | None = None):
    """
    Devuelve el PrecioServicio vigente para la combinación dada en 'fecha' (por defecto hoy).
    Reglas:
      - empresa exacta
      - sucursal exacta
      - servicio exacto
      - tipo_vehiculo exacto
      - vigencia_inicio <= fecha <= vigencia_fin (o fin null)
      - activo=True
    Prioriza la vigencia más reciente (mayor vigencia_inicio).
    """
    fecha = fecha or timezone.localdate()

    qs = (
        PrecioServicio.objects
        .filter(
            empresa=empresa,
            sucursal=sucursal,
            servicio=servicio,
            tipo_vehiculo=tipo_vehiculo,
            activo=True,
            vigencia_inicio__lte=fecha,
        )
        .filter(Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=fecha))
        .order_by("-vigencia_inicio", "-id")
    )

    return qs.first()


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
