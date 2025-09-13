# apps/pricing/services/pricing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import PrecioServicio


@dataclass(frozen=True)
class PrecioCmd:
    empresa: "org.Empresa"
    sucursal: "org.Sucursal"
    servicio: "catalog.Servicio"
    tipo_vehiculo: "vehicles.TipoVehiculo"
    precio: "decimal.Decimal"
    moneda: str = "ARS"
    vigencia_inicio: "datetime.date" = None
    vigencia_fin: Optional["datetime.date"] = None
    activo: bool = True


@transaction.atomic
def create_or_replace(cmd: PrecioCmd) -> PrecioServicio:
    """
    Crea un nuevo precio “vigente” para la combinación dada.
    Reglas:
      - Si hay un precio ACTIVO cuyo rango se solape, se ajusta su 'vigencia_fin'
        al día anterior a 'cmd.vigencia_inicio'.
      - Si existe un abierto (fin NULL) activo para la combinación, se cierra en
        'cmd.vigencia_inicio - 1' día.
      - Valida el modelo (clean + constraints).
    """
    if cmd.vigencia_inicio is None:
        cmd = PrecioCmd(
            **{**cmd.__dict__, "vigencia_inicio": timezone.localdate()})

    # Cerrar cualquier “abierto y activo” de la misma combinación (si existiera)
    abiertos = (
        PrecioServicio.objects
        .de_empresa(cmd.empresa)
        .de_combinacion(cmd.sucursal, cmd.servicio, cmd.tipo_vehiculo)
        .filter(activo=True, vigencia_fin__isnull=True)
    )
    if abiertos.exists():
        nuevo_fin = cmd.vigencia_inicio
        # Si el nuevo empieza hoy, cerramos al mismo día (regla conservadora).
        # Si querés que cierre al día anterior: nuevo_fin - timedelta(days=1)
        for p in abiertos:
            p.vigencia_fin = nuevo_fin
            p.full_clean()
            p.save(update_fields=["vigencia_fin", "actualizado"])

    # Ajustar solapados (activos) cuyo fin queda después del inicio nuevo
    solapados = (
        PrecioServicio.objects
        .de_empresa(cmd.empresa)
        .de_combinacion(cmd.sucursal, cmd.servicio, cmd.tipo_vehiculo)
        .filter(activo=True, vigencia_inicio__lte=cmd.vigencia_inicio)
        # fin >= inicio nuevo OR fin is NULL (ya tratados arriba)
        .exclude(vigencia_fin__lt=cmd.vigencia_inicio)
    )
    for p in solapados:
        if p.vigencia_fin is None or p.vigencia_fin >= cmd.vigencia_inicio:
            p.vigencia_fin = cmd.vigencia_inicio
            p.full_clean()
            p.save(update_fields=["vigencia_fin", "actualizado"])

    nuevo = PrecioServicio(
        empresa=cmd.empresa,
        sucursal=cmd.sucursal,
        servicio=cmd.servicio,
        tipo_vehiculo=cmd.tipo_vehiculo,
        precio=cmd.precio,
        moneda=cmd.moneda,
        vigencia_inicio=cmd.vigencia_inicio,
        vigencia_fin=cmd.vigencia_fin,
        activo=cmd.activo,
    )
    # Validación de dominio (multi-tenant, moneda, solapamientos, etc.)
    nuevo.full_clean()
    nuevo.save()
    return nuevo


@transaction.atomic
def update_price(instance: PrecioServicio, *, precio=None, moneda=None,
                 vigencia_inicio=None, vigencia_fin=None, activo=None) -> PrecioServicio:
    """
    Actualiza campos del precio existente. Si se cambia 'vigencia_inicio',
    se revalida solapamientos y consistencia.
    """
    if precio is not None:
        instance.precio = precio
    if moneda is not None:
        instance.moneda = moneda
    if vigencia_inicio is not None:
        instance.vigencia_inicio = vigencia_inicio
    if vigencia_fin is not None:
        instance.vigencia_fin = vigencia_fin
    if activo is not None:
        instance.activo = activo

    instance.full_clean()
    instance.save()
    return instance
