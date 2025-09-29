# apps/sales/fsm.py
"""
Definición de la máquina de estados OPERATIVA de Venta (solo PROCESO).

Separación de conceptos:
- PROCESO (esta FSM):   borrador | en_proceso | terminado | cancelado
- PAGO (payment_status): no_pagada | parcial | pagada   (se gestiona aparte)

Reglas de transición (proceso):
- Desde 'borrador' se puede:
    - iniciar trabajo → 'en_proceso'
    - finalizar directamente → 'terminado'   (permite flujos rápidos)
    - cancelar → 'cancelado'
- Desde 'en_proceso' se puede:
    - finalizar → 'terminado'
    - cancelar → 'cancelado'
- Desde 'terminado' se puede:
    - cancelar → 'cancelado'   (política conservadora; no se vuelve atrás)
- 'cancelado' es final.

Notas:
- El pago (prepago, parcial o al retiro) NO afecta estas transiciones.
- La lógica de emisión de comprobantes debe consultarse con payment_status,
  NO con el estado del proceso.
"""

from enum import Enum
from typing import Iterable, Union


class VentaEstado(str, Enum):
    BORRADOR = "borrador"
    EN_PROCESO = "en_proceso"
    TERMINADO = "terminado"
    CANCELADO = "cancelado"


# Transiciones válidas de PROCESO
_TRANSICIONES = {
    VentaEstado.BORRADOR:   {VentaEstado.EN_PROCESO, VentaEstado.TERMINADO, VentaEstado.CANCELADO},
    VentaEstado.EN_PROCESO: {VentaEstado.TERMINADO,  VentaEstado.CANCELADO},
    VentaEstado.TERMINADO:  {VentaEstado.CANCELADO},
    VentaEstado.CANCELADO:  set(),
}


def _coerce_estado(value: Union[str, VentaEstado]) -> VentaEstado:
    """Convierte cadenas o enums en VentaEstado; lanza ValueError si es inválido."""
    if isinstance(value, VentaEstado):
        return value
    return VentaEstado(str(value))


def transiciones_desde(desde: Union[str, VentaEstado]) -> Iterable[VentaEstado]:
    """Devuelve el conjunto de estados permitidos desde 'desde'."""
    estado = _coerce_estado(desde)
    return _TRANSICIONES.get(estado, set())


def puede_transicionar(desde: Union[str, VentaEstado], hacia: Union[str, VentaEstado]) -> bool:
    """Valida si se permite pasar de un estado a otro (PROCESO)."""
    try:
        estado_desde = _coerce_estado(desde)
        estado_hacia = _coerce_estado(hacia)
    except ValueError:
        return False
    return estado_hacia in _TRANSICIONES.get(estado_desde, set())


def es_final(estado: Union[str, VentaEstado]) -> bool:
    """True si el estado no tiene transiciones salientes."""
    try:
        e = _coerce_estado(estado)
    except ValueError:
        return False
    return len(_TRANSICIONES.get(e, set())) == 0
