# apps/sales/calculations.py
"""
Funciones puras para cálculos de totales de una Venta.
No acceden a la base de datos, operan sobre valores numéricos.

Nota sobre `saldo_pendiente`:
- Esta función devuelve `saldo_pendiente == total` como baseline.
- Si existen pagos, la capa de payments debe recalcular/sincronizar el saldo
  y actualizar `payment_status` (no_pagada/parcial/pagada).

Soporte de descuentos:
- Puede recibir `adjustments` (lista/iterable) con elementos que tengan al menos:
  - .kind: "item" | "order"
  - .mode: "percent" | "amount"
  - .value: Decimal / numérico
  - (opcional) .item_id o .item.id para asociar al ítem
- Si se provee `adjustments`, el parámetro `descuento` simple es ignorado.
- Orden de aplicación: primero descuentos por ítem, luego por venta.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Any, Dict, Tuple, List, Optional


Q = Decimal


def _D(x) -> Decimal:
    """Cast seguro a Decimal, tratando None/False/'' como 0."""
    try:
        return Q(x or 0)
    except Exception:
        return Q("0")


def _round2(v: Decimal) -> Decimal:
    return _D(v).quantize(Q("0.01"), rounding=ROUND_HALF_UP)


def _get(obj: Any, *attr_chain: str, default=None):
    """
    Acceso defensivo a atributos encadenados.
    _get(adj, "item_id") / _get(adj, "item", "id")
    """
    cur = obj
    for name in attr_chain:
        if cur is None:
            return default
        cur = getattr(cur, name, None)
    return default if cur is None else cur


def _item_subtotal(item: Any) -> Decimal:
    """
    Obtiene el subtotal del ítem:
    - Usa `item.subtotal` si existe,
    - De lo contrario intenta `cantidad * precio_unitario`.
    """
    st = getattr(item, "subtotal", None)
    if st is not None:
        return _D(st)
    cantidad = _D(getattr(item, "cantidad", 0))
    punit = _D(getattr(item, "precio_unitario", 0))
    return cantidad * punit


def _normalize_adjustments(
    adjustments: Optional[Iterable[Any]],
) -> Tuple[List[Any], Dict[Optional[int], List[Any]]]:
    """
    Retorna:
      - order_adjs: lista de ajustes con kind="order"
      - item_adjs_map: dict {item_id -> [ajustes]} para kind="item"
    """
    order_adjs: List[Any] = []
    item_adjs_map: Dict[Optional[int], List[Any]] = {}
    if not adjustments:
        return order_adjs, item_adjs_map

    for adj in adjustments:
        kind = (getattr(adj, "kind", "") or "").lower()
        if kind == "item":
            item_id = _get(adj, "item_id") or _get(
                adj, "item", "id") or _get(adj, "item", "pk")
            item_adjs_map.setdefault(item_id, []).append(adj)
        else:
            # default a "order" si no especifica correctamente
            order_adjs.append(adj)
    return order_adjs, item_adjs_map


def _resolver_descuento_sobre_base(base: Decimal, adjs: Iterable[Any]) -> Decimal:
    """
    Suma los descuentos (porcentaje/monto) sobre una `base`.
    Clampa el total para no superar la base.
    Ignora valores negativos.
    """
    base = _D(base)
    total_desc = Q("0")
    for a in (adjs or []):
        mode = (getattr(a, "mode", "") or "").lower()
        val = _D(getattr(a, "value", 0))
        if val < 0:
            # No permitir negativos (evita "recargos" por error)
            continue
        if mode == "percent":
            total_desc += base * val / Q("100")
        else:  # "amount" u otra cosa => tratamos como monto fijo
            total_desc += val
    # No exceder base
    if total_desc > base:
        total_desc = base
    return total_desc


def calcular_totales(
    items: Iterable[Any],
    descuento: Decimal = Q("0.00"),
    propina: Decimal = Q("0.00"),
    *,
    adjustments: Optional[Iterable[Any]] = None,
) -> Dict[str, Decimal]:
    """
    Calcula subtotal, descuento, propina, total y saldo_pendiente (baseline).

    Parámetros:
    - items: iterable de objetos con `.subtotal` o (`cantidad` y `precio_unitario`).
    - descuento: (LEGACY) monto total de descuento. Se ignora si se pasa `adjustments`.
    - propina: monto de propina.
    - adjustments: iterable de ajustes con (kind, mode, value, [item_id/item.id]).

    Reglas:
    - Si `adjustments` está presente, calcula descuento a partir de ellos:
      1) Descuentos por ÍTEM (sobre cada subtotal de ítem)
      2) Descuentos por VENTA (sobre el subtotal luego de aplicar los de ítem)
    - Si `adjustments` es None, usa `descuento` como monto total (clamp a subtotal).
    - Propina se suma al final y no entra en la base de descuentos.
    """
    items = list(items or [])
    propina = _D(propina)

    # 1) Subtotal base
    subtotales = [_item_subtotal(it) for it in items]
    subtotal_base = sum(subtotales, Q("0"))

    if adjustments is not None:
        # —— Nuevo flujo con ajustes —— #
        order_adjs, item_adjs_map = _normalize_adjustments(adjustments)

        # 2) Descuentos por ÍTEM
        desc_items = Q("0")
        for it, it_sub in zip(items, subtotales):
            it_id = getattr(it, "id", None) or getattr(it, "pk", None)
            it_desc = _resolver_descuento_sobre_base(
                it_sub, item_adjs_map.get(it_id, []))
            desc_items += it_desc

        # 3) Subtotal tras ítems
        subtotal_post_items = subtotal_base - desc_items
        if subtotal_post_items < 0:
            subtotal_post_items = Q("0")

        # 4) Descuentos por VENTA
        desc_order = _resolver_descuento_sobre_base(
            subtotal_post_items, order_adjs)

        descuento_total = desc_items + desc_order
    else:
        # —— Modo legacy sin `adjustments` —— #
        descuento_total = _D(descuento)
        if descuento_total < 0:
            descuento_total = Q("0")
        if descuento_total > subtotal_base:
            descuento_total = subtotal_base

    # 5) Total
    total = subtotal_base - descuento_total + propina
    if total < 0:
        total = Q("0")

    # 6) Redondeo estándar a 2 decimales
    subtotal_base = _round2(subtotal_base)
    descuento_total = _round2(descuento_total)
    propina = _round2(propina)
    total = _round2(total)

    return {
        "subtotal": subtotal_base,
        "descuento": descuento_total,
        "propina": propina,
        "total": total,
        "saldo_pendiente": total,  # baseline; payments lo ajusta después
    }
