# apps/accounts/services/memberships.py
from django.db import transaction
from .models import EmpresaMembership


@transaction.atomic
def ensure_membership(user, empresa, rol=EmpresaMembership.ROLE_OPERADOR):
    mem, created = EmpresaMembership.objects.get_or_create(
        user=user, empresa=empresa, defaults={"rol": rol})
    if not created and mem.rol != rol:
        mem.rol = rol
        mem.save(update_fields=["rol"])
    return mem
