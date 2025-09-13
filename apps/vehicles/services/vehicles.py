"""
services/vehicles.py — Casos de uso (mutaciones) para Vehiculo

Principios:
- Todas las funciones requieren 'empresa' (tenant) y, cuando aplica, 'user' para logging/auditoría.
- Validaciones de negocio aquí (además de las del Form): pertenencia a empresa, unicidad, etc.
- Usar transacciones atómicas para operaciones multi-escritura.
"""

import logging
from typing import Optional
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from apps.customers.models import Cliente
from ..models import Vehiculo
from ..validators import (
    normalizar_patente,
    validate_patente_format,
    ensure_patente_unique_in_company,
)

log = logging.getLogger(__name__)


def _assert_cliente_de_empresa(*, cliente: Cliente, empresa) -> None:
    if cliente.empresa_id != empresa.id:
        raise ValidationError(
            _("El cliente no pertenece a la empresa activa."))


@transaction.atomic
def crear_vehiculo(
    *,
    empresa,
    user,
    cliente: Cliente,
    tipo=None,
    marca: str = "",
    modelo: str = "",
    anio: Optional[int] = None,
    color: str = "",
    patente: str,
    notas: str = "",
    activo: bool = True,
) -> Vehiculo:
    """
    Alta de vehículo (tenant-safe).

    Reglas:
    - cliente debe pertenecer a empresa
    - patente formato AR y única por empresa (activos)
    """
    _assert_cliente_de_empresa(cliente=cliente, empresa=empresa)

    # Validación patente
    validate_patente_format(patente)
    patente_norm = normalizar_patente(patente)
    ensure_patente_unique_in_company(empresa=empresa, patente=patente_norm)

    veh = Vehiculo(
        empresa=empresa,
        cliente=cliente,
        tipo=tipo,
        marca=marca.strip(),
        modelo=modelo.strip(),
        anio=anio,
        color=color.strip(),
        patente=patente_norm,
        notas=notas.strip(),
        activo=activo,
    )
    veh.full_clean()  # valida modelo (incluye clean() que normaliza)
    veh.save()

    log.info("Vehículo creado id=%s empresa=%s user=%s",
             veh.id, empresa.id, getattr(user, "id", None))
    return veh


@transaction.atomic
def editar_vehiculo(
    *,
    empresa,
    user,
    vehiculo: Vehiculo,
    cliente: Optional[Cliente] = None,
    tipo=None,
    marca: Optional[str] = None,
    modelo: Optional[str] = None,
    anio: Optional[int] = None,
    color: Optional[str] = None,
    patente: Optional[str] = None,
    notas: Optional[str] = None,
    activo: Optional[bool] = None,
) -> Vehiculo:
    """
    Edición de un vehículo. Valida tenant y unicidad de patente si se modifica.
    """
    if vehiculo.empresa_id != empresa.id:
        raise PermissionDenied("No podés editar vehículos de otra empresa.")

    if cliente is not None:
        _assert_cliente_de_empresa(cliente=cliente, empresa=empresa)
        vehiculo.cliente = cliente

    if tipo is not None:
        vehiculo.tipo = tipo

    if marca is not None:
        vehiculo.marca = marca.strip()

    if modelo is not None:
        vehiculo.modelo = modelo.strip()

    if anio is not None:
        vehiculo.anio = anio

    if color is not None:
        vehiculo.color = color.strip()

    if patente is not None:
        validate_patente_format(patente)
        patente_norm = normalizar_patente(patente)
        ensure_patente_unique_in_company(
            empresa=empresa,
            patente=patente_norm,
            exclude_pk=vehiculo.pk,
        )
        vehiculo.patente = patente_norm

    if notas is not None:
        vehiculo.notas = (notas or "").strip()

    if activo is not None:
        vehiculo.activo = bool(activo)

    vehiculo.full_clean()
    vehiculo.save()

    log.info("Vehículo editado id=%s empresa=%s user=%s",
             vehiculo.id, empresa.id, getattr(user, "id", None))
    return vehiculo


@transaction.atomic
def activar_vehiculo(*, empresa, user, vehiculo: Vehiculo) -> Vehiculo:
    """
    Activa (soft-undelete) un vehículo.
    Verifica colisión de patente antes de activar.
    """
    if vehiculo.empresa_id != empresa.id:
        raise PermissionDenied("No podés activar vehículos de otra empresa.")
    if vehiculo.activo:
        return vehiculo

    ensure_patente_unique_in_company(
        empresa=empresa,
        patente=vehiculo.patente,
        exclude_pk=vehiculo.pk,
        only_active=True,
    )
    vehiculo.activo = True
    vehiculo.full_clean()
    vehiculo.save()

    log.info("Vehículo activado id=%s empresa=%s user=%s",
             vehiculo.id, empresa.id, getattr(user, "id", None))
    return vehiculo


@transaction.atomic
def desactivar_vehiculo(*, empresa, user, vehiculo: Vehiculo) -> Vehiculo:
    """
    Desactiva (soft delete) un vehículo.
    """
    if vehiculo.empresa_id != empresa.id:
        raise PermissionDenied(
            "No podés desactivar vehículos de otra empresa.")
    if not vehiculo.activo:
        return vehiculo

    vehiculo.activo = False
    vehiculo.full_clean()
    vehiculo.save()

    log.info("Vehículo desactivado id=%s empresa=%s user=%s",
             vehiculo.id, empresa.id, getattr(user, "id", None))
    return vehiculo


@transaction.atomic
def transferir_propietario(*, empresa, user, vehiculo: Vehiculo, nuevo_cliente: Cliente) -> Vehiculo:
    """
    Cambia el propietario de un vehículo (mantiene historial en notas si querés).
    """
    if vehiculo.empresa_id != empresa.id:
        raise PermissionDenied(
            "No podés transferir vehículos de otra empresa.")
    _assert_cliente_de_empresa(cliente=nuevo_cliente, empresa=empresa)

    anterior = vehiculo.cliente
    vehiculo.cliente = nuevo_cliente
    vehiculo.full_clean()
    vehiculo.save()

    log.info(
        "Vehículo transferido id=%s de cliente=%s a cliente=%s empresa=%s user=%s",
        vehiculo.id, anterior_id := getattr(anterior, "id", None),
        getattr(nuevo_cliente, "id", None), empresa.id, getattr(
            user, "id", None)
    )
    return vehiculo
