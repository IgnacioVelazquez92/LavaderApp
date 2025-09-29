# apps/sales/calculations.py
"""
Funciones puras para cálculos de totales de una Venta.
No acceden a la base de datos, operan sobre valores numéricos.

Nota sobre `saldo_pendiente`:
- Esta función devuelve `saldo_pendiente == total` como baseline.
- Si existen pagos, la capa de payments debe recalcular/sincronizar el saldo
  y actualizar `payment_status` (no_pagada/parcial/pagada).
"""

from decimal import Decimal


def calcular_totales(items, descuento=Decimal("0.00"), propina=Decimal("0.00")):
    """
    Calcula subtotal, descuento, propina, total.
    - `items`: iterable de objetos con `.subtotal` (p. ej. VentaItem).
    - No considera pagos; `saldo_pendiente` se devuelve igual a `total` (baseline).
    """
    subtotal = sum((Decimal(getattr(item, "subtotal", 0))
                   for item in items), Decimal("0.00"))
    descuento = Decimal(descuento or 0)
    propina = Decimal(propina or 0)

    total = subtotal - descuento + propina
    if total < 0:
        total = Decimal("0.00")

    return {
        "subtotal": subtotal,
        "descuento": descuento,
        "propina": propina,
        "total": total,
        "saldo_pendiente": total,  # baseline; payments lo ajusta después
    }
