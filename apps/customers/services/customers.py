# apps/customers/services/customers.py
from typing import Mapping, Any
from django.core.exceptions import ValidationError
from ..models import Cliente


def create_customer(*, empresa, data: Mapping[str, Any], user=None) -> Cliente:
    """
    Crea Cliente bajo una empresa. 'data' viene típicamente de un form limpio.
    """
    obj = Cliente(empresa=empresa, creado_por=user, **data)
    obj.full_clean()
    obj.save()
    return obj


def update_customer(*, obj: Cliente, data: Mapping[str, Any]) -> Cliente:
    """
    Actualiza campos del Cliente recibido.
    """
    for k, v in data.items():
        setattr(obj, k, v)
    obj.full_clean()
    obj.save()
    return obj


def soft_delete_customer(*, obj: Cliente) -> Cliente:
    """
    Baja lógica. (No se borra físicamente por integridad con ventas/vehículos.)
    """
    obj.activo = False
    obj.save(update_fields=["activo"])
    return obj
