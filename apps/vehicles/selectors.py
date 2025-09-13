"""
selectors.py — Lecturas/consultas del módulo Vehicles

Convenciones:
- Todas las funciones reciben 'empresa' (tenant) explícito.
- No hacen mutaciones (solo SELECT).
- Devuelven QuerySets o valores inmutables (tuplas, dicts simples).
"""

from typing import Optional, Iterable, Tuple
from django.db.models import Q, QuerySet, Count
from apps.customers.models import Cliente
from .models import Vehiculo, TipoVehiculo
from .validators import normalizar_patente


# ----------------------------
# Tipos de vehículo
# ----------------------------

def listar_tipos_vehiculo(*, empresa, solo_activos: bool = True) -> QuerySet[TipoVehiculo]:
    """
    Lista tipos de vehículo de la empresa.
    """
    qs = TipoVehiculo.objects.filter(empresa=empresa)
    if solo_activos:
        qs = qs.filter(activo=True)
    return qs.order_by("nombre")


def obtener_tipo_por_slug(*, empresa, slug: str) -> Optional[TipoVehiculo]:
    """
    Trae un TipoVehiculo por slug dentro de la empresa (o None si no existe).
    """
    try:
        return TipoVehiculo.objects.get(empresa=empresa, slug=slug)
    except TipoVehiculo.DoesNotExist:
        return None


# ----------------------------
# Vehículos
# ----------------------------

def buscar_vehiculos(
    *,
    empresa,
    q: Optional[str] = None,
    cliente: Optional[Cliente] = None,
    solo_activos: bool = True,
) -> QuerySet[Vehiculo]:
    """
    Búsqueda flexible por:
      - patente (acepta con/sin guiones/espacios, se normaliza)
      - marca / modelo (icontains)
      - cliente (FK)

    Ejemplo:
        qs = buscar_vehiculos(empresa=request.empresa_activa, q="ab-123-cd")
    """
    qs = Vehiculo.objects.select_related(
        "cliente", "tipo").filter(empresa=empresa)
    if solo_activos:
        qs = qs.filter(activo=True)

    if cliente:
        qs = qs.filter(cliente=cliente)

    if q:
        q_norm = normalizar_patente(q)
        # Buscar por patente exacta normalizada o por coincidencia en marca/modelo
        qs = qs.filter(
            Q(patente=q_norm) |
            Q(marca__icontains=q) |
            Q(modelo__icontains=q)
        )

    return qs.order_by("-actualizado", "patente")


def vehiculos_de_cliente(*, empresa, cliente: Cliente, solo_activos: bool = True) -> QuerySet[Vehiculo]:
    """
    Lista vehículos de un cliente (validando tenant).
    """
    qs = Vehiculo.objects.filter(empresa=empresa, cliente=cliente)
    if solo_activos:
        qs = qs.filter(activo=True)
    return qs.order_by("-actualizado", "patente")


def obtener_por_patente(*, empresa, patente: str, incluir_inactivos: bool = False) -> Optional[Vehiculo]:
    """
    Obtiene un vehículo por patente normalizada dentro de la empresa.
    """
    p = normalizar_patente(patente)
    qs = Vehiculo.objects.select_related(
        "cliente", "tipo").filter(empresa=empresa, patente=p)
    if not incluir_inactivos:
        qs = qs.filter(activo=True)
    try:
        return qs.get()
    except Vehiculo.DoesNotExist:
        return None


def stats_por_tipo(*, empresa, solo_activos: bool = True) -> QuerySet:
    """
    Devuelve un QS con agregados: cantidad de vehículos por tipo.
    Útil para tarjetas KPI en el dashboard.
    """
    qs = Vehiculo.objects.filter(empresa=empresa)
    if solo_activos:
        qs = qs.filter(activo=True)
    return qs.values("tipo__nombre").annotate(total=Count("id")).order_by("-total")


def existe_patente(*, empresa, patente: str) -> bool:
    """
    Chequeo rápido de existencia (activo) por patente en la empresa.
    """
    from .validators import normalizar_patente
    return Vehiculo.objects.filter(
        empresa=empresa,
        patente=normalizar_patente(patente),
        activo=True
    ).exists()


def contar_activos(*, empresa) -> int:
    """
    Cantidad de vehículos activos en la empresa.
    """
    return Vehiculo.objects.filter(empresa=empresa, activo=True).count()
