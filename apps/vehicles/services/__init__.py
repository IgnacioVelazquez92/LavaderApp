from .vehicles import (
    crear_vehiculo,
    editar_vehiculo,
    activar_vehiculo,
    desactivar_vehiculo,
    transferir_propietario,
)
from .types import (
    crear_tipo_vehiculo,
    editar_tipo_vehiculo,
    activar_tipo_vehiculo,
    desactivar_tipo_vehiculo,
)

__all__ = [
    # vehículos
    "crear_vehiculo",
    "editar_vehiculo",
    "activar_vehiculo",
    "desactivar_vehiculo",
    "transferir_propietario",
    # tipos
    "crear_tipo_vehiculo",
    "editar_tipo_vehiculo",
    "activar_tipo_vehiculo",
    "desactivar_tipo_vehiculo",
]
