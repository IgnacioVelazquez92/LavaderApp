# apps/cashbox/services/totals.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum, Q, F
from django.utils import timezone

from apps.cashbox.models import CierreCaja
# asume existencia: Pago(venta, medio, monto, es_propina, creado_en)
from apps.payments.models import Pago
# Nota: MedioPago está en apps.payments.models también (FK de Pago.medio)


@dataclass(frozen=True)
class TotalesMetodo:
    """DTO in-memory para un renglón de totales por método de pago."""
    medio: "apps.payments.models.MedioPago"
    monto: Decimal        # total cobrado (no incluye propinas)
    propinas: Decimal     # total de propinas


def _rango_queryset_pagos(cierre: CierreCaja, hasta) -> "django.db.models.QuerySet[Pago]":
    """
    Construye el queryset base de Pagos para el rango del cierre.

    Reglas:
    - Filtra Pagos de la **misma empresa** del cierre a través de Venta → Empresa.
    - Limita a la **misma sucursal** del cierre (Venta.sucursal = cierre.sucursal).
    - Ventana temporal: [cierre.abierto_en, hasta].
    """
    # Seguridad: si hasta es None, considerar now()
    if hasta is None:
        hasta = timezone.now()

    qs = (
        Pago.objects.select_related(
            "medio", "venta", "venta__sucursal", "venta__empresa")
        .filter(
            venta__empresa_id=cierre.empresa_id,
            venta__sucursal_id=cierre.sucursal_id,
            creado_en__gte=cierre.abierto_en,
            creado_en__lte=hasta,
        )
    )
    return qs


def sumar_pagos_por_metodo(*, cierre: CierreCaja, hasta) -> list[TotalesMetodo]:
    """
    Devuelve los totales agrupados por método de pago para el rango del cierre.

    - `monto` suma SOLO pagos con `es_propina=False`.
    - `propinas` suma SOLO pagos con `es_propina=True`.
    - Si un método tiene solo propinas (o solo montos), el otro componente se considera 0.

    Args:
        cierre: CierreCaja (abierto o cerrado).
        hasta: datetime aware que marca el límite superior del rango (incluyente).

    Returns:
        list[TotalesMetodo]
    """
    qs = _rango_queryset_pagos(cierre=cierre, hasta=hasta)

    # Agregamos por método con sumas condicionadas
    # Usamos una sola agregación por método para performance.
    agregados = (
        qs.values("medio_id", "medio__nombre")
        .annotate(
            monto_total=Sum("monto", filter=Q(es_propina=False)),
            propinas_total=Sum("monto", filter=Q(es_propina=True)),
        )
        .order_by("medio__nombre")
    )

    # Materializamos DTOs; también necesitamos el objeto 'medio' (podemos traérnoslo del primer Pago o de FK)
    # Para minimizar queries, reconstruimos un dict medio_id -> medio usando un pequeño prefeteo:
    medio_ids = [row["medio_id"] for row in agregados]
    from apps.payments.models import MedioPago  # import local para evitar ciclos
    medios = {m.id: m for m in MedioPago.objects.filter(id__in=medio_ids)}

    resultados: list[TotalesMetodo] = []
    for row in agregados:
        medio = medios.get(row["medio_id"])
        monto = row["monto_total"] or Decimal("0.00")
        propinas = row["propinas_total"] or Decimal("0.00")
        resultados.append(TotalesMetodo(
            medio=medio, monto=monto, propinas=propinas))

    return resultados
