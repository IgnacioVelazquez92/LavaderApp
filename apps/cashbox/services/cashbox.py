# apps/cashbox/services/cashbox.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from apps.cashbox.models import TurnoCaja, TurnoCajaTotal
from apps.cashbox.services.totals import TotalesMetodo, sumar_pagos_por_metodo


# ---------- Errores de dominio ----------
class TurnoAbiertoExistenteError(ValidationError):
    """Se intentó abrir un turno cuando ya existe uno ABIERTO para la sucursal."""
    code = "turno_abierto_existente"


class TurnoNoAbiertoError(ValidationError):
    """Se intentó cerrar un turno que ya estaba cerrado (o no existe)."""
    code = "turno_no_abierto"


# ---------- DTOs ----------
@dataclass(frozen=True)
class AperturaTurnoResult:
    turno: TurnoCaja
    creado: bool


@dataclass(frozen=True)
class CierreTurnoResult:
    turno: TurnoCaja
    totales: List[TotalesMetodo]


# ---------- Servicios ----------
def abrir_turno(
    *,
    empresa,
    sucursal,
    user,
    responsable_nombre: str = "",
    observaciones: str = "",
    abierto_en=None
) -> TurnoCaja:
    """
    Abre un turno para la sucursal activa. En tu modelo permitimos 1 turno abierto por sucursal.
    """
    if sucursal.empresa_id != empresa.id:
        raise PermissionDenied(
            "La sucursal no pertenece a la empresa indicada.")

    if abierto_en is None:
        abierto_en = timezone.now()

    existe_abierto = TurnoCaja.objects.filter(
        empresa=empresa, sucursal=sucursal, cerrado_en__isnull=True
    ).exists()
    if existe_abierto:
        raise TurnoAbiertoExistenteError(
            "Ya existe un turno abierto en esta sucursal.")

    with transaction.atomic():
        turno = TurnoCaja.objects.create(
            empresa=empresa,
            sucursal=sucursal,
            abierto_por=user,
            abierto_en=abierto_en,
            responsable_nombre=(responsable_nombre or "").strip(),
            observaciones=(observaciones or "").strip(),
        )
    return turno


# ---------- Helpers de resolución de campos ----------
def _resolver_campos_totales(model_cls) -> Tuple[str, str, Optional[str], bool]:
    """
    Devuelve (campo_monto, campo_propinas, campo_medio_nombre|None, usa_fk_medio: bool)
    Detecta nombres en TurnoCajaTotal para compatibilidad con distintos esquemas.

    En TU DB actual (ver dump del shell) esperamos:
      - medio_nombre
      - monto_teorico
      - propinas_teoricas
    """
    field_names = {
        f.name for f in model_cls._meta.get_fields() if getattr(f, "concrete", False)
    }

    # Incluir tus campos reales primero
    candidatos_monto = [
        "monto_teorico",
        # fallback genéricos por si cambia el esquema más adelante:
        "monto", "monto_sin_propina", "importe", "importe_sin_propina",
        "total_sin_propina", "total", "importe_neto", "monto_neto",
    ]
    candidatos_propinas = [
        "propinas_teoricas",
        # fallbacks
        "propinas", "propina", "tips", "propinas_total", "monto_propina",
    ]

    monto_field = next((n for n in candidatos_monto if n in field_names), None)
    prop_field = next(
        (n for n in candidatos_propinas if n in field_names), None)

    usa_fk_medio = "medio" in field_names
    medio_nombre_field = "medio_nombre" if "medio_nombre" in field_names else None

    if not monto_field or not prop_field:
        raise ValidationError(
            [
                "TurnoCajaTotal no tiene campos de importes esperados.",
                f"Campos actuales: {sorted(field_names)}",
                "Busqué alguno de estos para 'monto': " +
                ", ".join(candidatos_monto),
                "y alguno de estos para 'propinas': " +
                ", ".join(candidatos_propinas),
            ]
        )

    if not (usa_fk_medio or medio_nombre_field):
        raise ValidationError(
            [
                "TurnoCajaTotal debe tener 'medio' (FK) o 'medio_nombre' (CharField).",
                f"Campos actuales: {sorted(field_names)}",
            ]
        )

    return monto_field, prop_field, medio_nombre_field, usa_fk_medio


# ---------- Servicios de alto nivel ----------
def cerrar_turno(
    *,
    turno: TurnoCaja,
    user,
    monto_contado_total=None,
    cerrado_en: Optional[timezone.datetime] = None,
    notas_append: Optional[str] = None,
    recalcular_y_guardar_totales: bool = True,
) -> CierreTurnoResult:
    """
    Cierra un turno ABIERTO y persiste totales por método en TurnoCajaTotal.
    Mapea explícitamente a tus columnas actuales: medio_nombre, monto_teorico, propinas_teoricas.
    """
    if not turno.esta_abierto:
        raise TurnoNoAbiertoError("El turno ya estaba cerrado.")

    if cerrado_en is None:
        cerrado_en = timezone.now()
    if cerrado_en < turno.abierto_en:
        raise ValidationError(
            "La fecha/hora de cierre no puede ser anterior a la de apertura.")

    # Descubrir cómo se llaman los campos en TU modelo (con soporte a futuros cambios)
    monto_field, prop_field, medio_nombre_field, usa_fk_medio = _resolver_campos_totales(
        TurnoCajaTotal)

    with transaction.atomic():
        turno = TurnoCaja.objects.select_for_update().get(pk=turno.pk)

        totales_list: List[TotalesMetodo] = []
        if recalcular_y_guardar_totales:
            totales_list = sumar_pagos_por_metodo(
                turno=turno, hasta=cerrado_en)

            # Reemplazar totales guardados
            TurnoCajaTotal.objects.filter(turno=turno).delete()

            objs = []
            for t in totales_list:
                # t.medio puede ser instancia (MedioPago) o string (nombre)
                obj_kwargs = {
                    "turno": turno,
                    monto_field: t.monto,
                    prop_field: t.propinas,
                }

                if usa_fk_medio and hasattr(t.medio, "pk"):
                    obj_kwargs["medio"] = t.medio
                else:
                    nombre = getattr(t.medio, "nombre", None) if hasattr(
                        t.medio, "__dict__") else None
                    valor_nombre = nombre if nombre else str(t.medio)
                    if medio_nombre_field:
                        obj_kwargs[medio_nombre_field] = valor_nombre
                    else:
                        # Por seguridad, no debería ocurrir (lo validamos arriba)
                        raise ValidationError(
                            "No hay campo para identificar el medio de pago en TurnoCajaTotal.")

                objs.append(TurnoCajaTotal(**obj_kwargs))

            TurnoCajaTotal.objects.bulk_create(objs, batch_size=50)

        # Sello de cierre
        if notas_append:
            turno.observaciones = (
                turno.observaciones + "\n" + notas_append).strip()
        turno.cerrado_en = cerrado_en
        turno.cerrado_por = user

        fields_to_update = ["cerrado_en", "cerrado_por", "observaciones"]
        if hasattr(turno, "monto_contado_total") and monto_contado_total is not None:
            turno.monto_contado_total = monto_contado_total
            fields_to_update.append("monto_contado_total")

        turno.save(update_fields=fields_to_update)

    return CierreTurnoResult(turno=turno, totales=totales_list)
