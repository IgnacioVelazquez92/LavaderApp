# apps/cashbox/services/totals.py
from __future__ import annotations
from django.db.models import Sum
from datetime import datetime, date, timedelta

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Iterable, Optional, Any

from django.db.models import Sum, Q, Value
from django.db.models.functions import Coalesce

from apps.payments.models import Pago, MedioPago
from apps.cashbox.models import TurnoCaja
from django.utils import timezone

# ======================================================
# DTO
# ======================================================


@dataclass(frozen=True)
class TotalesMetodo:
    """
    medio: puede ser instancia de MedioPago (preferido) o un str con el nombre.
    monto: total sin propina (Decimal)
    propinas: total de propinas (Decimal)
    """
    medio: Any
    monto: Decimal
    propinas: Decimal

    @property
    def total_incl_propina(self) -> Decimal:
        return (self.monto or Decimal("0")) + (self.propinas or Decimal("0"))


# ======================================================
# Helpers internos
# ======================================================

def _sumar_pagos_grouped(qs) -> List[TotalesMetodo]:
    """
    Agrupa un queryset de Pago por medio y devuelve TotalesMetodo usando
    aggregates filtrados (no hay doble annotate ni colisiones).
    """
    # Traemos IDs y nombres en el group-by
    rows = (
        qs.values("medio_id", "medio__nombre")
        .annotate(
            monto_sin_propina=Coalesce(
                Sum("monto", filter=Q(es_propina=False)), Value(Decimal("0.00"))
            ),
            propinas_total=Coalesce(
                Sum("monto", filter=Q(es_propina=True)), Value(Decimal("0.00"))
            ),
        )
        .order_by("medio__nombre")
    )

    ids = [r["medio_id"] for r in rows if r["medio_id"] is not None]
    medio_map = {m.id: m for m in MedioPago.objects.filter(id__in=ids)}

    result: List[TotalesMetodo] = []
    for r in rows:
        medio_obj = medio_map.get(r["medio_id"])
        medio_val = medio_obj if medio_obj is not None else (
            r["medio__nombre"] or "—")

        result.append(
            TotalesMetodo(
                medio=medio_val,
                monto=Decimal(r["monto_sin_propina"] or 0),
                propinas=Decimal(r["propinas_total"] or 0),
            )
        )
    return result


def _qs_pagos_turno(*, turno: TurnoCaja, hasta=None):
    """
    Base queryset de pagos para un turno.
    Nota: todos los pagos que registra el sistema asignan Pago.turno (en services.payments).
    """
    qs = Pago.objects.filter(turno=turno).select_related("medio")
    # Si quisieras tolerar pagos viejos sin turno asignado, podrías usar el rango de fechas:
    # desde, _ = turno.rango()
    # qs = qs.filter(creado_en__gte=desde, creado_en__lte=(hasta or timezone.now()))
    if hasta is not None:
        qs = qs.filter(creado_en__lte=hasta)
    return qs


# ======================================================
# API pública del servicio
# ======================================================

def sumar_pagos_por_metodo(*, turno: TurnoCaja, hasta=None) -> List[TotalesMetodo]:
    """
    Suma pagos por método de un turno, separando monto (sin propina) y propinas.
    Usa aggregates filtrados para evitar colisiones de nombres/anotaciones.
    """
    qs = _qs_pagos_turno(turno=turno, hasta=hasta)
    return _sumar_pagos_grouped(qs)


def preview_totales_turno(*, turno: TurnoCaja) -> List[TotalesMetodo]:
    """
    Preview “en vivo” para un turno (hasta ahora).
    Reutiliza el mismo agrupado (no persiste nada).
    """
    return sumar_pagos_por_metodo(turno=turno, hasta=None)


# --- CIERRE Z / SUMAS POR RANGO (sin turno) ------------------------------


def _acotar_dia_aware(fecha: date) -> tuple[datetime, datetime]:
    """
    Devuelve (desde, hasta) aware para el día local indicado.
    """
    d = fecha or timezone.localdate()
    inicio = timezone.make_aware(datetime(d.year, d.month, d.day, 0, 0, 0))
    fin = timezone.make_aware(datetime(d.year, d.month, d.day, 23, 59, 59))
    return inicio, fin


def sumar_pagos_por_metodo_en_rango(
    *,
    empresa,
    sucursal=None,
    desde: datetime,
    hasta: datetime,
) -> list[TotalesMetodo]:
    """
    Suma pagos por método en el rango [desde, hasta], separando monto (no propina) y propinas.
    NO usa TurnoCaja, es para cierres Z u otros reportes por fecha.

    Retorna list[TotalesMetodo] con .medio (str: nombre del medio), .monto, .propinas.
    """
    from apps.payments.models import Pago  # import local para evitar ciclos

    qs = Pago.objects.filter(
        venta__empresa=empresa,
        creado_en__gte=desde,
        creado_en__lte=hasta,
    )
    if sucursal is not None:
        qs = qs.filter(venta__sucursal=sucursal)

    # Agrupamos por medio y por flag de propina; OJO: no hagas annotate() con nombres que choquen.
    rows = (
        qs.select_related("medio")
          .values("medio__nombre", "es_propina")
          .annotate(total=Sum("monto"))
    )

    acc: dict[str, dict] = {}
    for r in rows:
        nombre = r["medio__nombre"] or "—"
        total = r["total"] or 0
        is_tip = bool(r["es_propina"])

        item = acc.setdefault(
            nombre, {"medio": nombre, "monto": 0, "propinas": 0})
        if is_tip:
            item["propinas"] += total
        else:
            item["monto"] += total

    # Convertimos a TotalesMetodo (mantenemos medio como str; tu cierre ya maneja str o obj)
    out: list[TotalesMetodo] = []
    for data in sorted(acc.values(), key=lambda x: x["medio"]):
        out.append(TotalesMetodo(
            medio=data["medio"], monto=data["monto"], propinas=data["propinas"]))
    return out


def cierre_z_totales_dia(
    *,
    empresa,
    sucursal=None,
    fecha: date | None = None,
) -> list[TotalesMetodo]:
    """
    Azúcar para Cierre Z diario: agrupa pagos del día 'fecha' (local).
    """
    desde, hasta = _acotar_dia_aware(fecha or timezone.localdate())
    return sumar_pagos_por_metodo_en_rango(
        empresa=empresa, sucursal=sucursal, desde=desde, hasta=hasta
    )
