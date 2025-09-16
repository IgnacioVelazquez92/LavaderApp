# apps/sales/fsm.py
"""
Definición de la máquina de estados de Venta.
Reglas acordadas:
- Se puede cobrar antes de terminar el trabajo:
  borrador/en_proceso → pagado
- Una vez cobrado, cuando termina el trabajo:
  pagado → terminado
- terminado y cancelado son finales operativos (no vuelven a pagado).
"""

from enum import Enum
from typing import Iterable, Union


class VentaEstado(str, Enum):
    BORRADOR = "borrador"
    EN_PROCESO = "en_proceso"
    TERMINADO = "terminado"
    PAGADO = "pagado"
    CANCELADO = "cancelado"


# Transiciones válidas (según circuito actualizado)
_TRANSICIONES = {
    VentaEstado.BORRADOR:   {VentaEstado.EN_PROCESO, VentaEstado.PAGADO, VentaEstado.CANCELADO},
    VentaEstado.EN_PROCESO: {VentaEstado.TERMINADO, VentaEstado.PAGADO,  VentaEstado.CANCELADO},
    VentaEstado.PAGADO:     {VentaEstado.TERMINADO,                        VentaEstado.CANCELADO},
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
    """Valida si se permite pasar de un estado a otro."""
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
