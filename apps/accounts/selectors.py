# apps/accounts/selectors.py
from .models import EmpresaMembership


def memberships_for(user):
    return (
        EmpresaMembership.objects
        .select_related("empresa")
        .filter(user=user)
        .order_by("empresa__nombre")
    )
