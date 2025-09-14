# apps/sales/services/sales.py
"""
Comandos principales sobre el modelo Venta.
Capa de mutaciones: no renderiza, no maneja requests.
"""

from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.sales.models import Venta
from apps.sales.calculations import calcular_totales
from apps.sales.fsm import puede_transicionar, VentaEstado


@transaction.atomic
def crear_venta(*, empresa, sucursal, cliente, vehiculo, creado_por, notas="") -> Venta:
    """
    Crea una nueva Venta en estado 'borrador'.
    """
    venta = Venta.objects.create(
        empresa=empresa,
        sucursal=sucursal,
        cliente=cliente,
        vehiculo=vehiculo,
        estado=VentaEstado.BORRADOR,
        notas=notas,
        creado_por=creado_por,
    )
    return venta


@transaction.atomic
def actualizar_venta(*, venta: Venta, notas: str = None) -> Venta:
    """
    Actualiza campos simples de la venta (ej. notas).
    """
    if notas is not None:
        venta.notas = notas
    venta.save(update_fields=["notas", "actualizado"])
    return venta


@transaction.atomic
def recalcular_totales(*, venta: Venta) -> Venta:
    """
    Recalcula todos los totales de una venta a partir de sus ítems.
    """
    data = calcular_totales(venta.items.all(), venta.descuento, venta.propina)
    for field, value in data.items():
        setattr(venta, field, value)
    venta.save(update_fields=list(data.keys()) + ["actualizado"])
    return venta


@transaction.atomic
def cambiar_estado(*, venta: Venta, nuevo_estado: str) -> Venta:
    """
    Transición de estado con validación FSM.
    """
    if not puede_transicionar(venta.estado, nuevo_estado):
        raise ValidationError(
            f"No se puede pasar de {venta.estado} a {nuevo_estado}")
    venta.estado = nuevo_estado
    venta.save(update_fields=["estado", "actualizado"])
    return venta


def finalizar_venta(*, venta: Venta) -> Venta:
    """Marca la venta como terminada (bloquea ítems)."""
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.TERMINADO)


def cancelar_venta(*, venta: Venta) -> Venta:
    """Marca la venta como cancelada."""
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.CANCELADO)


def marcar_pagada(*, venta: Venta) -> Venta:
    """Marca la venta como pagada (usado por módulo payments)."""
    return cambiar_estado(venta=venta, nuevo_estado=VentaEstado.PAGADO)
