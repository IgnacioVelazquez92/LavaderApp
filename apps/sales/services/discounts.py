# apps/sales/services/discounts.py
"""
Servicios de descuentos/promociones (ajustes) para Ventas.

Conceptos:
- SalesAdjustment: línea de ajuste aplicada a la venta o a un ítem (percent/amount).
- Promotion: definición reutilizable (ventana de validez, scope y valor).

Reglas clave:
- Orden de aplicación en el cálculo (ver calculations.py):
  1) Ajustes por ÍTEM
  2) Ajustes por VENTA
- Estados ajustables: solo en 'borrador' y 'en_proceso'.
- Los ajustes afectan `venta.descuento` y, por ende, `venta.total`.
- Payments recalcula `saldo_pendiente` con base en `total`.

Este módulo NO toca la FSM directamente.
"""

from __future__ import annotations
from apps.org.permissions import has_empresa_perm, Perm
from django.core.exceptions import PermissionDenied

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional
from decimal import Decimal as _D
from django.db import transaction, models, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from apps.sales.models import Venta, VentaItem, SalesAdjustment, Promotion
from apps.sales.services.sales import recalcular_totales

# ---------------------------------------------------------------------
# Config & helpers
# ---------------------------------------------------------------------

# dónde se puede agregar/quitar ajustes
AJUSTABLE_STATES = {"borrador", "en_proceso"}

KIND_ORDER = SalesAdjustment.KIND_ORDER
KIND_ITEM = SalesAdjustment.KIND_ITEM
MODE_PERCENT = SalesAdjustment.MODE_PERCENT
MODE_AMOUNT = SalesAdjustment.MODE_AMOUNT
SOURCE_PROMO = SalesAdjustment.SOURCE_PROMO

SOURCE_MANUAL = "manual"

SOURCE_PAYMENT = "payment"


def _D(x) -> Decimal:
    try:
        return Decimal(x or 0)
    except Exception:
        return Decimal("0")


def _validate_kind(kind: str) -> None:
    if kind not in (KIND_ORDER, KIND_ITEM):
        raise ValidationError("Ámbito de promoción inválido.")


def _validate_mode_value(mode: str, value) -> None:
    try:
        v = _D(value)
    except Exception:
        raise ValidationError("Valor de promoción inválido.")
    if mode == MODE_PERCENT:
        if v < 0 or v > 100:
            raise ValidationError("El porcentaje debe estar entre 0 y 100.")
    elif mode == MODE_AMOUNT:
        if v < 0:
            raise ValidationError("El monto debe ser ≥ 0.")
    else:
        raise ValidationError("Modo de promoción inválido.")


def _assert_ajustable(venta: Venta) -> None:
    if venta.estado not in ("borrador", "en_proceso"):
        raise ValidationError(
            "No se pueden aplicar promociones en este estado.")


def _promos_base_queryset(empresa, sucursal):
    qs = Promotion.objects.filter(empresa=empresa, activo=True)
    if sucursal is not None:
        qs = qs.filter(models.Q(sucursal__isnull=True)
                       | models.Q(sucursal=sucursal))
    return qs


def _promo_esta_vigente(promo: Promotion, fecha=None) -> bool:
    """
    Usa el método del modelo (valido_desde/valido_hasta, activo).
    Trabaja con date (no datetime).
    """
    fecha = fecha or timezone.localdate()
    return promo.esta_vigente(fecha=fecha)


def _ajuste_existente_mismo_origen(venta: Venta, source: str) -> bool:
    return venta.adjustments.filter(source=source).exists()


def _require_perm(actor, empresa, perm):
    if actor is None:
        # si tu flujo SIEMPRE tiene usuario, podés endurecer esto
        raise PermissionDenied("Acción no autorizada.")
    if not has_empresa_perm(actor, empresa, perm):
        raise PermissionDenied("No tenés permisos para esta acción.")


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------


@transaction.atomic
def agregar_descuento_manual_venta(
    *,
    venta: Venta,
    mode: str,
    value: Decimal,
    motivo: str = "",
    actor=None,
) -> SalesAdjustment:
    """
    Crea un ajuste MANUAL a nivel VENTA.
    """
    _require_perm(actor, venta.empresa, Perm.SALES_DISCOUNT_ADD)
    _assert_ajustable(venta)
    _validate_mode_value(mode, value)

    adj = SalesAdjustment.objects.create(
        venta=venta,
        kind=KIND_ORDER,
        mode=mode,
        value=_D(value),
        source=SOURCE_MANUAL,
        motivo=motivo.strip()[:160] if motivo else "Descuento manual",
        aplicado_por=actor,
    )
    recalcular_totales(venta=venta)
    return adj


@transaction.atomic
def agregar_descuento_manual_item(
    *,
    item: VentaItem,
    mode: str,
    value: Decimal,
    motivo: str = "",
    actor=None,
) -> SalesAdjustment:
    """
    Crea un ajuste MANUAL a nivel ÍTEM.
    """
    venta = item.venta
    _require_perm(actor, venta.empresa, Perm.SALES_DISCOUNT_ADD)
    _assert_ajustable(venta)
    _validate_mode_value(mode, value)

    adj = SalesAdjustment.objects.create(
        venta=venta,
        item=item,
        kind=KIND_ITEM,
        mode=mode,
        value=_D(value),
        source=SOURCE_MANUAL,
        motivo=motivo.strip()[:160] if motivo else "Descuento manual",
        aplicado_por=actor,
    )
    recalcular_totales(venta=venta)
    return adj


@transaction.atomic
def eliminar_ajuste(*, ajuste: SalesAdjustment) -> None:
    """
    Elimina un ajuste (manual/promo/payment).
    """
    venta = ajuste.venta
    _require_perm(actor, venta.empresa, Perm.SALES_DISCOUNT_ADD)
    _assert_ajustable(venta)
    ajuste.delete()
    recalcular_totales(venta=venta)


def listar_promociones_vigentes_para_venta(*, venta: Venta):
    """
    Promos scope='order' activas, por empresa y sucursal (o sin sucursal),
    vigentes a la fecha, que cumplan min_total y NO estén ya aplicadas
    a nivel venta.
    """
    hoy = timezone.localdate()

    qs = (
        Promotion.objects.filter(
            empresa=venta.empresa,
            scope=KIND_ORDER,
            activo=True,
        )
        .filter(Q(sucursal__isnull=True) | Q(sucursal=venta.sucursal))
        .order_by("prioridad", "id")
    )

    # Excluir ya aplicadas (a nivel venta → item IS NULL)
    applied_ids = SalesAdjustment.objects.filter(
        venta=venta, promotion__isnull=False, item__isnull=True
    ).values_list("promotion_id", flat=True)
    qs = qs.exclude(id__in=list(applied_ids))

    # Filtrar por vigencia y min_total
    promos = []
    for p in qs:
        if not _promo_esta_vigente(p, hoy):
            continue
        if p.min_total is not None:
            subtotal = _D(venta.subtotal or 0)
            if subtotal < _D(p.min_total):
                continue
        promos.append(p)
    return promos


def listar_promociones_vigentes_para_item(*, venta: Venta):
    """
    Promos scope='item' activas, por empresa y sucursal (o sin sucursal),
    vigentes a la fecha. La exclusión de duplicados por ítem se evalúa al aplicar.
    """
    hoy = timezone.localdate()

    qs = (
        Promotion.objects.filter(
            empresa=venta.empresa,
            scope=KIND_ITEM,
            activo=True,
        )
        .filter(Q(sucursal__isnull=True) | Q(sucursal=venta.sucursal))
        .order_by("prioridad", "id")
    )

    return [p for p in qs if _promo_esta_vigente(p, hoy)]


@transaction.atomic
def aplicar_promocion(
    *,
    venta: Venta,
    promo: Promotion,
    item: Optional[VentaItem] = None,
    motivo: str = "",
    actor=None,
) -> SalesAdjustment:
    """
    Aplica una promoción vigente. Valida scope y estado de venta.
    - Para scope='item' se requiere `item`.
    - Para scope='order' NO debe pasarse `item`.
    - Evita duplicados por (venta,promo) y por (venta,item,promo).
    """

    _require_perm(actor, venta.empresa, getattr(
        Perm, "SALES_PROMO_APPLY", None))

    _assert_ajustable(venta)
    if not _promo_esta_vigente(promo):
        raise ValidationError("La promoción no está vigente.")
    if promo.empresa_id != venta.empresa_id:
        raise ValidationError("La promoción no corresponde a esta empresa.")

    if promo.scope == KIND_ITEM:
        if item is None or item.venta_id != venta.id:
            raise ValidationError(
                "Esta promoción es por ítem; seleccione un ítem válido.")
    elif promo.scope == KIND_ORDER:
        if item is not None:
            raise ValidationError(
                "Esta promoción es por venta; no debe pasarse ítem.")
    else:
        _validate_kind(promo.scope)

    _validate_mode_value(promo.mode, promo.value)

    # Pre-check anti-duplicados (mensaje amable)
    qs = SalesAdjustment.objects.filter(venta=venta, promotion=promo)
    qs = qs.filter(
        item__isnull=True) if promo.scope == KIND_ORDER else qs.filter(item=item)
    if qs.exists():
        raise ValidationError(
            "La promoción ya fue aplicada en esta venta/ítem.")

    adj_kwargs = dict(
        venta=venta,
        kind=promo.scope,
        mode=promo.mode,
        value=_D(promo.value),
        source=SOURCE_PROMO,
        promotion=promo,
        motivo=(motivo.strip()[:160] if motivo else f"Promo: {promo.nombre}"),
        aplicado_por=actor,
    )
    if promo.scope == KIND_ITEM:
        adj_kwargs["item"] = item

    try:
        adj = SalesAdjustment.objects.create(**adj_kwargs)
    except IntegrityError:
        # Defensa extra por race conditions o por diferencias de soporte en índices parciales
        raise ValidationError(
            "La promoción ya fue aplicada en esta venta/ítem.")

    recalcular_totales(venta=venta)
    return adj


@transaction.atomic
def aplicar_descuento_por_metodo_pago_si_corresponde(
    *,
    venta: Venta,
    payment_method_code: str,
    actor=None,
) -> Optional[SalesAdjustment]:
    """
    Aplica automáticamente un descuento ligado a método de pago (si hay promo configurada).
    - No duplica: si ya existe un ajuste con source='payment', no hace nada.
    - Toma la promo válida de menor prioridad (número más bajo) y, en empate, mayor valor.
    """
    _assert_ajustable(venta)

    if _ajuste_existente_mismo_origen(venta, SOURCE_PAYMENT):
        return None

    if not payment_method_code:
        return None

    hoy = timezone.localdate()
    qs = _promos_base_queryset(venta.empresa, venta.sucursal).filter(
        scope=KIND_ORDER,
        payment_method_code=payment_method_code,
    )

    promos = [p for p in qs if _promo_esta_vigente(p, hoy)]
    if not promos:
        return None

    # Elegimos por prioridad ASC (menor = más prioritario), luego value DESC
    promos.sort(key=lambda p: (p.prioridad, -float(p.value)))

    promo = promos[0]
    _validate_mode_value(promo.mode, promo.value)

    adj = SalesAdjustment.objects.create(
        venta=venta,
        kind=KIND_ORDER,
        mode=promo.mode,
        value=_D(promo.value),
        source=SOURCE_PAYMENT,
        promotion=promo,
        motivo=f"Descuento por pago: {payment_method_code}",
        aplicado_por=actor,
    )
    recalcular_totales(venta=venta)
    return adj


# ---------------------------------------------------------------------
# Utilidades para UI / reportes (opcionales)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class AjusteResumen:
    id: int
    kind: str           # order | item
    mode: str           # percent | amount
    value: Decimal
    source: str         # manual | promo | payment
    motivo: str
    item_id: Optional[int]
    promotion_id: Optional[int]
    promotion_nombre: Optional[str]


def obtener_resumen_ajustes(*, venta: Venta) -> List[AjusteResumen]:
    """
    Devuelve una lista simple para la UI/reportes del detalle de ajustes.
    """
    res: List[AjusteResumen] = []
    qs = venta.adjustments.select_related(
        "item", "promotion").order_by("creado", "id")
    for a in qs:
        res.append(
            AjusteResumen(
                id=a.id,
                kind=a.kind,
                mode=a.mode,
                value=_D(a.value),
                source=a.source,
                motivo=a.motivo or "",
                item_id=a.item_id,
                promotion_id=a.promotion_id,
                promotion_nombre=getattr(a.promotion, "nombre", None),
            )
        )
    return res
