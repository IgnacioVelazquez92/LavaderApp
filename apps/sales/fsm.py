# apps/sales/fsm.py
"""
Definición de la máquina de estados de Venta.
Controla transiciones válidas y evita estados inconsistentes.
"""

from enum import Enum


class VentaEstado(str, Enum):
    BORRADOR = "borrador"
    EN_PROCESO = "en_proceso"
    TERMINADO = "terminado"
    PAGADO = "pagado"
    CANCELADO = "cancelado"


# Transiciones válidas
TRANSICIONES = {
    VentaEstado.BORRADOR: [VentaEstado.EN_PROCESO, VentaEstado.CANCELADO],
    VentaEstado.EN_PROCESO: [VentaEstado.TERMINADO, VentaEstado.CANCELADO],
    VentaEstado.TERMINADO: [VentaEstado.PAGADO, VentaEstado.CANCELADO],
    VentaEstado.PAGADO: [],       # estado final
    VentaEstado.CANCELADO: [],    # estado final
}


def puede_transicionar(desde: str, hacia: str) -> bool:
    """Valida si se permite pasar de un estado a otro."""
    try:
        return hacia in TRANSICIONES[VentaEstado(desde)]
    except Exception:
        return False
