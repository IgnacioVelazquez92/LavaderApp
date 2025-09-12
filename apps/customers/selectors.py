# apps/customers/selectors.py
from django.db.models import Q
from .models import Cliente


def customers_qs(empresa, q: str | None = None, estado: str = "activos"):
    """
    Devuelve queryset de clientes filtrado por empresa + búsqueda + estado.
    """
    qs = Cliente.objects.filter(empresa=empresa)
    if estado == "activos":
        qs = qs.filter(activo=True)
    elif estado == "inactivos":
        qs = qs.filter(activo=False)

    if q:
        q = q.strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(apellido__icontains=q)
                | Q(razon_social__icontains=q)
                | Q(email__icontains=q)
                | Q(documento__icontains=q)
                | Q(tel_wpp__icontains=q)
                | Q(tel_busqueda__icontains=q)
            )

    return qs.select_related("empresa").order_by("razon_social", "apellido", "nombre")
