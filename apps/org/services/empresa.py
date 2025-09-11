# apps/org/services/empresa.py

from ..models import Empresa, EmpresaConfig
from django.contrib.auth import get_user_model

User = get_user_model()


def crear_empresa(nombre: str, subdominio: str, user: User, logo=None) -> Empresa:
    """
    Crea una empresa y asigna al usuario como admin.
    (La membresía se crea desde accounts.services.memberships.ensure_membership)
    """
    empresa = Empresa.objects.create(
        nombre=nombre, subdominio=subdominio, logo=logo)
    # Configuración inicial por defecto
    EmpresaConfig.objects.create(
        empresa=empresa, clave="moneda", valor={"simbolo": "$"})
    return empresa


def actualizar_empresa(empresa: Empresa, **datos) -> Empresa:
    """
    Actualiza los datos de la empresa.
    """
    for field, value in datos.items():
        setattr(empresa, field, value)
    empresa.save()
    return empresa
