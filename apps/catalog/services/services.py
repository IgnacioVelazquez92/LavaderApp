# apps/catalog/services/services.py
from __future__ import annotations

from typing import Optional, Tuple
from dataclasses import dataclass

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models.functions import Lower

from apps.catalog.models import Servicio
from apps.org.models import Empresa


@dataclass(frozen=True)
class ServiceResult:
    """Resultado estándar de mutaciones de Servicio."""
    servicio: Servicio
    created: bool = False
    updated_fields: Tuple[str, ...] = ()


def _assert_scoping(servicio: Servicio, empresa: Empresa) -> None:
    """Garantiza que el objeto pertenezca a la empresa activa."""
    if servicio.empresa_id != empresa.id:
        raise PermissionDenied("El servicio no pertenece a la empresa activa.")


def _assert_unique_nombre(empresa: Empresa, nombre: str, exclude_pk: Optional[int] = None) -> None:
    """Valida unicidad case-insensitive de nombre por empresa (error amigable)."""
    qs = (Servicio.objects.filter(empresa=empresa)
          .annotate(nombre_ci=Lower("nombre"))
          .filter(nombre_ci=(nombre or "").strip().lower()))
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError(
            {"nombre": "Ya existe un servicio con ese nombre en esta empresa."})


def _assert_unique_slug(empresa: Empresa, slug: Optional[str], exclude_pk: Optional[int] = None) -> None:
    """Valida unicidad de slug por empresa (si se proporcionó manualmente)."""
    slug = (slug or "").strip()
    if not slug:
        return
    qs = Servicio.objects.filter(empresa=empresa, slug=slug)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError(
            {"slug": "El slug ya está en uso en esta empresa."})


@transaction.atomic
def crear_servicio(
    *,
    empresa: Empresa,
    nombre: str,
    descripcion: str = "",
    slug: Optional[str] = None,
    # reservado para auditoría si se necesita
    creado_por: Optional[int] = None,
) -> ServiceResult:
    """
    Crea un Servicio activo dentro de `empresa`.

    Reglas:
    - `nombre` obligatorio y único (case-insensitive) por empresa.
    - `slug` único por empresa si se pasa (si se omite, el modelo lo autogenera).
    - `activo=True` al crear.
    """
    nombre = (nombre or "").strip()
    descripcion = (descripcion or "").strip()
    if not nombre:
        raise ValidationError({"nombre": "El nombre es obligatorio."})

    _assert_unique_nombre(empresa, nombre)
    _assert_unique_slug(empresa, slug)

    servicio = Servicio(
        empresa=empresa,
        nombre=" ".join(nombre.split()),
        descripcion=descripcion,
        slug=(slug or "").strip() or "",
        activo=True,
    )
    # Hooks de auditoría podrían ir aquí (e.g., servicio._actor_id = creado_por)
    servicio.full_clean()  # valida constraints de modelo
    servicio.save()        # autogenera slug si estaba vacío

    return ServiceResult(servicio=servicio, created=True)


@transaction.atomic
def editar_servicio(
    *,
    empresa: Empresa,
    servicio_id: int,
    nombre: Optional[str] = None,
    descripcion: Optional[str] = None,
    slug: Optional[str] = None,
    activo: Optional[bool] = None,
    editado_por: Optional[int] = None,
) -> ServiceResult:
    """
    Edita campos del Servicio asegurando scoping por empresa y unicidad.

    Solo actualiza campos provistos (patch semantics).
    """
    servicio = Servicio.objects.select_for_update().get(pk=servicio_id)
    _assert_scoping(servicio, empresa)

    updated: list[str] = []

    if nombre is not None:
        nombre_n = (nombre or "").strip()
        if not nombre_n:
            raise ValidationError({"nombre": "El nombre es obligatorio."})
        _assert_unique_nombre(empresa, nombre_n, exclude_pk=servicio.pk)
        servicio.nombre = " ".join(nombre_n.split())
        updated.append("nombre")

    if descripcion is not None:
        servicio.descripcion = (descripcion or "").strip()
        updated.append("descripcion")

    if slug is not None:
        slug_n = (slug or "").strip()
        _assert_unique_slug(empresa, slug_n, exclude_pk=servicio.pk)
        # puede quedar vacío; el modelo no lo regenera en edición si ya existe
        servicio.slug = slug_n
        updated.append("slug")

    if activo is not None:
        servicio.activo = bool(activo)
        updated.append("activo")

    # Auditoría opcional: servicio._actor_id = editado_por
    servicio.full_clean()
    servicio.save(update_fields=[*updated, "actualizado"] if updated else None)

    return ServiceResult(servicio=servicio, updated_fields=tuple(updated))


@transaction.atomic
def desactivar_servicio(*, empresa: Empresa, servicio_id: int, motivo: str | None = None) -> ServiceResult:
    """
    Marca un servicio como inactivo (soft-archive).
    """
    servicio = Servicio.objects.select_for_update().get(pk=servicio_id)
    _assert_scoping(servicio, empresa)

    if not servicio.activo:
        return ServiceResult(servicio=servicio, updated_fields=())

    servicio.activo = False
    # podría registrarse `motivo` en un futuro campo de auditoría
    servicio.full_clean()
    servicio.save(update_fields=["activo", "actualizado"])

    return ServiceResult(servicio=servicio, updated_fields=("activo",))


@transaction.atomic
def activar_servicio(*, empresa: Empresa, servicio_id: int) -> ServiceResult:
    """
    Reactiva un servicio previamente inactivo.
    """
    servicio = Servicio.objects.select_for_update().get(pk=servicio_id)
    _assert_scoping(servicio, empresa)

    if servicio.activo:
        return ServiceResult(servicio=servicio, updated_fields=())

    servicio.activo = True
    servicio.full_clean()
    servicio.save(update_fields=["activo", "actualizado"])

    return ServiceResult(servicio=servicio, updated_fields=("activo",))
