# apps/org/services/sucursal.py

from ..models import Sucursal, Empresa


def crear_sucursal(empresa: Empresa, nombre: str, direccion: str, codigo_interno: str) -> Sucursal:
    return Sucursal.objects.create(
        empresa=empresa,
        nombre=nombre,
        direccion=direccion,
        codigo_interno=codigo_interno,
    )


def actualizar_sucursal(sucursal: Sucursal, **datos) -> Sucursal:
    for field, value in datos.items():
        setattr(sucursal, field, value)
    sucursal.save()
    return sucursal
