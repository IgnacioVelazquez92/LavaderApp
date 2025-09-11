# apps/org/permissions.py

from django.core.exceptions import PermissionDenied
from apps.accounts.models import EmpresaMembership


def require_empresa_admin(user, empresa):
    if not EmpresaMembership.objects.filter(user=user, empresa=empresa, rol="admin").exists():
        raise PermissionDenied(
            "No tienes permisos de administrador en esta empresa")
    return True
