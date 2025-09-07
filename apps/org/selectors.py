from typing import Iterable
from django.contrib.auth import get_user_model
from .models import Empresa

User = get_user_model()


def empresas_para_usuario(user: User) -> Iterable[Empresa]:
    """
    Devuelve las empresas donde el usuario tiene membresía.
    Importa EmpresaMembership en tiempo de ejecución para evitar ciclos.
    """
    from apps.accounts.models import EmpresaMembership  # import local para evitar import circular
    empresa_ids = (
        EmpresaMembership.objects
        .filter(user=user)
        .values_list("empresa_id", flat=True)
    )
    return Empresa.objects.filter(id__in=empresa_ids, activo=True).order_by("nombre")
