# apps/sales/services/lifecycle.py
"""
Hooks de ciclo de vida de la Venta.
Se ejecutan cuando hay transiciones de estado importantes.
Ejemplo: notificar al cliente cuando la venta pasa a 'terminado'.
"""

from apps.sales.models import Venta
from apps.sales.services.sales import cambiar_estado
from apps.sales.fsm import VentaEstado


def on_finalizar(venta: Venta):
    """
    Lógica al finalizar una venta.
    Ej: notificar al cliente que su vehículo está listo.
    """
    # TODO: integrar con apps.notifications
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.TERMINADO)


def on_pagada(venta: Venta):
    """
    Lógica al marcar como pagada.
    Ej: disparar emisión de comprobante en apps.invoicing.
    """
    # TODO: integrar con apps.invoicing
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.PAGADO)


def on_cancelar(venta: Venta):
    """
    Lógica al cancelar una venta.
    Ej: revertir reservas de stock o loggear motivo.
    """
    # TODO: side-effects adicionales si aplica
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.CANCELADO)
