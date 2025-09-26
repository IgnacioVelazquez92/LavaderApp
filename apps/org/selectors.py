# apps/org/selectors.py

from typing import List
from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.accounts.models import EmpresaMembership
from .models import Empresa, Sucursal

# Gating centralizado (SaaS)
from apps.saas.limits import (
    can_create_empresa,
    can_create_sucursal,
    can_add_usuario_a_empresa,
    can_add_empleado,
)

User = get_user_model()


def empresas_para_usuario(user: User) -> QuerySet[Empresa]:
    """
    Devuelve las EMPRESAS ACTIVAS donde el usuario tiene membresía ACTIVA.
    (evita mostrar compañías deshabilitadas o memberships inactivas)
    """
    return (
        Empresa.objects
        .filter(
            memberships__user=user,
            memberships__activo=True,
            activo=True,
        )
        .distinct()
    )


def sucursales_de(empresa: Empresa) -> QuerySet[Sucursal]:
    """Sucursales de una empresa (no filtra por 'activo' porque el modelo no lo expone)."""
    return empresa.sucursales.all()


# -------------------------------
# Wrappers de gating (SaaS limits)
# -------------------------------

def gate_crear_empresa(user: User):
    """Devuelve el GateResult para crear empresa (tiene .should_block() y .message)."""
    return can_create_empresa(user)


def gate_crear_sucursal(empresa: Empresa):
    """GateResult para crear sucursal en la empresa dada."""
    return can_create_sucursal(empresa)


def gate_agregar_usuario(empresa: Empresa):
    """GateResult para agregar usuarios (membresías) a la empresa."""
    return can_add_usuario_a_empresa(empresa)


def gate_agregar_empleado(sucursal: Sucursal):
    """GateResult para agregar empleados asignados a la sucursal dada."""
    return can_add_empleado(sucursal)


# -------------------------------
# Booleans convenientes para UI
# -------------------------------

def puede_crear_mas_empresas(user: User) -> bool:
    """
    **DEPRECATED**: antes usaba un tope estático por settings.
    Ahora delega en el Gate centralizado.
    """
    gate = can_create_empresa(user)
    return not gate.should_block()


def puede_crear_sucursal(empresa: Empresa) -> bool:
    gate = can_create_sucursal(empresa)
    return not gate.should_block()


def puede_agregar_usuario(empresa: Empresa) -> bool:
    gate = can_add_usuario_a_empresa(empresa)
    return not gate.should_block()


def puede_agregar_empleado(sucursal: Sucursal) -> bool:
    gate = can_add_empleado(sucursal)
    return not gate.should_block()


# -------------------------------
# Contadores útiles (panel/UX)
# -------------------------------

def contar_miembros_activos(empresa: Empresa) -> int:
    """Cantidad de membresías activas en la empresa (usuarios activos en la compañía)."""
    return EmpresaMembership.objects.filter(empresa=empresa, activo=True).count()


def contar_sucursales(empresa: Empresa) -> int:
    return Sucursal.objects.filter(empresa=empresa).count()


def contar_empleados_en_sucursal(sucursal: Sucursal) -> int:
    """Cantidad de membresías activas asignadas a la sucursal dada."""
    return EmpresaMembership.objects.filter(
        empresa=sucursal.empresa,
        sucursal_asignada=sucursal,
        activo=True,
    ).count()
