# apps/cashbox/services/cashbox.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from apps.cashbox.models import CierreCaja, CierreCajaTotal
from apps.cashbox.services.totals import TotalesMetodo, sumar_pagos_por_metodo


# ---------- Errores de dominio ----------
class CierreAbiertoExistenteError(ValidationError):
    """Se intentó abrir un cierre cuando ya existe uno ABIERTO para la sucursal."""
    code = "cierre_abierto_existente"


class CierreNoAbiertoError(ValidationError):
    """Se intentó cerrar un cierre que ya estaba cerrado (o no existe)."""
    code = "cierre_no_abierto"


# ---------- DTOs / respuestas ----------
@dataclass(frozen=True)
class AperturaResult:
    cierre: CierreCaja
    # True si se creó uno nuevo, False si devolvemos el abierto existente (opcional)
    creado: bool


@dataclass(frozen=True)
class CierreResult:
    cierre: CierreCaja
    totales: list[TotalesMetodo]


# ---------- Servicios de alto nivel ----------
def abrir_cierre(*, empresa, sucursal, usuario, abierto_en=None, notas: str = "") -> AperturaResult:
    """
    Abre un Cierre de Caja para (empresa, sucursal).

    Reglas:
    - Solo puede haber **un cierre ABIERTO** por sucursal (enforced por constraint + validación).
    - Guarda quién lo abrió y cuándo.

    Args:
        empresa: org.Empresa (objeto)
        sucursal: org.Sucursal (objeto) — debe pertenecer a `empresa`.
        usuario: User — quien abre.
        abierto_en: datetime aware (default now) — normalmente now().
        notas: texto opcional.

    Returns:
        AperturaResult(cierre, creado=True)

    Raises:
        CierreAbiertoExistenteError: si ya hay un cierre abierto para `sucursal`.
        PermissionDenied: si `sucursal.empresa != empresa`.
    """
    if sucursal.empresa_id != empresa.id:
        raise PermissionDenied(
            "La sucursal no pertenece a la empresa indicada.")

    if abierto_en is None:
        abierto_en = timezone.now()

    # Validación rápida (además del UniqueConstraint)
    existe_abierto = CierreCaja.objects.filter(
        sucursal=sucursal, cerrado_en__isnull=True).exists()
    if existe_abierto:
        raise CierreAbiertoExistenteError(
            "Ya existe un cierre abierto en esta sucursal.")

    with transaction.atomic():
        cierre = CierreCaja.objects.create(
            empresa=empresa,
            sucursal=sucursal,
            usuario=usuario,
            abierto_en=abierto_en,
            notas=notas or "",
        )
    return AperturaResult(cierre=cierre, creado=True)


def cerrar_cierre(
    *,
    cierre: CierreCaja,
    actor,
    cerrado_en=None,
    notas_append: str | None = None,
    recalcular_y_guardar_totales: bool = True,
) -> CierreResult:
    """
    Cierra un Cierre de Caja ABIERTO y persiste los totales por método.

    Pasos:
    1) Valida que el cierre esté ABIERTO.
    2) Determina `cerrado_en` (default now).
    3) Calcula totales por método sobre pagos de `apps.payments.Pago` en el rango [abierto_en, cerrado_en].
    4) Persiste `CierreCajaTotal` (reemplaza si existieran).
    5) Sella `cerrado_en` y `cerrado_por`.

    Args:
        cierre: CierreCaja ABIERTO (mismo tenant que el actor).
        actor: User que cierra.
        cerrado_en: datetime aware (default now()).
        notas_append: opcional para agregar texto al final de `notas`.
        recalcular_y_guardar_totales: si False, solo sella cerrado_en (no recomendado en operación normal).

    Returns:
        CierreResult(cierre, totales=list[TotalesMetodo])

    Raises:
        CierreNoAbiertoError: si el cierre ya estaba cerrado.
        ValidationError: si `cerrado_en < abierto_en`.
    """
    if not cierre.esta_abierta:
        raise CierreNoAbiertoError("El cierre ya estaba cerrado.")

    if cerrado_en is None:
        cerrado_en = timezone.now()

    if cerrado_en < cierre.abierto_en:
        raise ValidationError(
            "La fecha/hora de cierre no puede ser anterior a la de apertura.")

    with transaction.atomic():
        # Refrescar lock por seguridad (SELECT ... FOR UPDATE via update/save)
        cierre = CierreCaja.objects.select_for_update().get(pk=cierre.pk)

        # Cálculo de totales (si corresponde)
        totales_list: list[TotalesMetodo] = []
        if recalcular_y_guardar_totales:
            totales_list = sumar_pagos_por_metodo(
                cierre=cierre, hasta=cerrado_en)

            # Reemplazar totales persistidos
            CierreCajaTotal.objects.filter(cierre=cierre).delete()
            CierreCajaTotal.objects.bulk_create(
                [
                    CierreCajaTotal(
                        cierre=cierre,
                        medio=t.medio,
                        monto=t.monto,
                        propinas=t.propinas,
                    )
                    for t in totales_list
                ],
                batch_size=50,
                ignore_conflicts=False,
            )

        # Sello de cierre
        if notas_append:
            cierre.notas = (cierre.notas + "\n" + notas_append).strip()
        cierre.cerrado_en = cerrado_en
        cierre.cerrado_por = actor
        cierre.save(update_fields=[
                    "notas", "cerrado_en", "cerrado_por", "actualizado_en"])

    return CierreResult(cierre=cierre, totales=totales_list)


def preview_totales_actuales(*, cierre: CierreCaja, hasta=None) -> list[TotalesMetodo]:
    """
    Calcula **en memoria** los totales por método para el cierre ABIERTO *hasta ahora* (o `hasta`).

    Útil para mostrar en el formulario de cierre antes de confirmar.

    Args:
        cierre: CierreCaja (debe estar ABIERTO).
        hasta: datetime aware (default now()).

    Returns:
        list[TotalesMetodo]
    """
    if not cierre.esta_abierta:
        # Si ya está cerrado, el preview es redundante; igual se puede llamar con hasta=cierre.cerrado_en
        pass
    if hasta is None:
        hasta = timezone.now()
    return sumar_pagos_por_metodo(cierre=cierre, hasta=hasta)
