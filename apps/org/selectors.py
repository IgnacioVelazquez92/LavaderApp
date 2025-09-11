# apps/org/selectors.py

from django.conf import settings
from typing import List
from django.contrib.auth import get_user_model
from .models import Empresa, Sucursal
from apps.accounts.models import EmpresaMembership

User = get_user_model()


def empresas_para_usuario(user: User) -> List[Empresa]:
    """
    Devuelve todas las empresas a las que el usuario tiene membresía.
    """
    return Empresa.objects.filter(memberships__user=user)


def sucursales_de(empresa: Empresa) -> List[Sucursal]:
    return empresa.sucursales.all()


# apps/org/selectors.py (agregar al final)


def puede_crear_mas_empresas(user) -> bool:
    max_emp = getattr(settings, "SAAS_MAX_EMPRESAS_POR_USUARIO", 1)
    actuales = EmpresaMembership.objects.filter(user=user).count()
    return actuales < max_emp
