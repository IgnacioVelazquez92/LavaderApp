# apps/sales/calculations.py
"""
Funciones puras para cálculos de totales de una Venta.
No acceden a la base de datos, operan sobre valores numéricos.
"""

from decimal import Decimal


def calcular_totales(items, descuento=Decimal("0.00"), propina=Decimal("0.00")):
    """
    Calcula subtotal, descuento, propina, total.
    - `items`: iterable de objetos con `.subtotal` (p. ej. VentaItem).
    """
    subtotal = sum((item.subtotal for item in items), Decimal("0.00"))
    total = subtotal - descuento + propina
    if total < 0:
        total = Decimal("0.00")
    return {
        "subtotal": subtotal,
        "descuento": descuento,
        "propina": propina,
        "total": total,
        "saldo_pendiente": total,  # al inicio coincide con total
    }
