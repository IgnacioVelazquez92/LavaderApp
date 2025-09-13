"""
services/types.py — Casos de uso para TipoVehiculo
"""

import logging
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from ..models import TipoVehiculo

log = logging.getLogger(__name__)


@transaction.atomic
def crear_tipo_vehiculo(*, empresa, user, nombre: str, slug: str, activo: bool = True) -> TipoVehiculo:
    """
    Alta de tipo de vehículo. Unicidad (empresa, slug).
    """
    nombre = (nombre or "").strip()
    slug = (slug or "").strip()
    if not nombre or not slug:
        raise ValidationError(_("Nombre y slug son obligatorios."))

    if TipoVehiculo.objects.filter(empresa=empresa, slug=slug).exists():
        raise ValidationError(
            _("Ya existe un tipo con este slug en tu empresa."))

    t = TipoVehiculo(empresa=empresa, nombre=nombre, slug=slug, activo=activo)
    t.full_clean()
    t.save()
    log.info("TipoVehiculo creado id=%s empresa=%s user=%s",
             t.id, empresa.id, getattr(user, "id", None))
    return t


@transaction.atomic
def editar_tipo_vehiculo(*, empresa, user, tipo: TipoVehiculo, nombre: str, slug: str, activo: bool) -> TipoVehiculo:
    """
    Edición de tipo. Valida tenant y unicidad de slug.
    """
    if tipo.empresa_id != empresa.id:
        raise PermissionDenied("No podés editar tipos de otra empresa.")

    nombre = (nombre or "").strip()
    slug = (slug or "").strip()
    if not nombre or not slug:
        raise ValidationError(_("Nombre y slug son obligatorios."))

    qs = TipoVehiculo.objects.filter(
        empresa=empresa, slug=slug).exclude(pk=tipo.pk)
    if qs.exists():
        raise ValidationError(
            _("Ya existe un tipo con este slug en tu empresa."))

    tipo.nombre = nombre
    tipo.slug = slug
    tipo.activo = bool(activo)
    tipo.full_clean()
    tipo.save()
    log.info("TipoVehiculo editado id=%s empresa=%s user=%s",
             tipo.id, empresa.id, getattr(user, "id", None))
    return tipo


@transaction.atomic
def activar_tipo_vehiculo(*, empresa, user, tipo: TipoVehiculo) -> TipoVehiculo:
    if tipo.empresa_id != empresa.id:
        raise PermissionDenied("No podés activar tipos de otra empresa.")
    if tipo.activo:
        return tipo
    tipo.activo = True
    tipo.full_clean()
    tipo.save()
    log.info("TipoVehiculo activado id=%s empresa=%s user=%s",
             tipo.id, empresa.id, getattr(user, "id", None))
    return tipo


@transaction.atomic
def desactivar_tipo_vehiculo(*, empresa, user, tipo: TipoVehiculo) -> TipoVehiculo:
    if tipo.empresa_id != empresa.id:
        raise PermissionDenied("No podés desactivar tipos de otra empresa.")
    if not tipo.activo:
        return tipo
    tipo.activo = False
    tipo.full_clean()
    tipo.save()
    log.info("TipoVehiculo desactivado id=%s empresa=%s user=%s",
             tipo.id, empresa.id, getattr(user, "id", None))
    return tipo
