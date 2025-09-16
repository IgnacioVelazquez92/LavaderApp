# lavaderos/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.org.models import Empresa, Sucursal


def _first_empresa_for_user(user):
    """
    Devuelve la primera Empresa ACTIVA a la que el usuario pertenece, sin asumir
    nombres de relaciones. Soporta:
      1) Modelo de membership apps.accounts.EmpresaMembership (si existe).
      2) FK de dueño en Empresa: owner / propietario / creado_por.
      3) M2M en Empresa: usuarios / members / miembros / users.
      4) Fallback: primera empresa activa global (si no hay relación definida).
    """
    qs_activa = Empresa.objects.filter(activo=True)

    # 1) Membership externo (si existe)
    try:
        from apps.accounts.models import EmpresaMembership  # opcional
        empresa_ids = (
            EmpresaMembership.objects
            .filter(user=user)
            .values_list("empresa_id", flat=True)
        )
        emp = qs_activa.filter(id__in=list(empresa_ids)).order_by("id").first()
        if emp:
            return emp
    except Exception:
        pass

    # 2) FK "dueño" común
    for fk in ("owner", "propietario", "creado_por"):
        if fk in [f.name for f in Empresa._meta.get_fields()]:
            emp = qs_activa.filter(**{fk: user}).order_by("id").first()
            if emp:
                return emp

    # 3) M2M "usuarios/miembros"
    for m2m in ("usuarios", "members", "miembros", "users"):
        if m2m in [f.name for f in Empresa._meta.get_fields()]:
            emp = qs_activa.filter(**{f"{m2m}": user}).order_by("id").first()
            if emp:
                return emp

    # 4) Fallback más seguro: ninguna relación encontrada
    return qs_activa.order_by("id").first()


class TenancyMiddleware(MiddlewareMixin):
    """
    Inyecta en cada request autenticado:
      - request.empresa_activa: Empresa o None
      - request.sucursal_activa: Sucursal o None (de la empresa_activa)

    Reglas:
      - Si no hay empresa_id en sesión: fija la primera empresa activa asociada al usuario
        (membership / dueño / m2m). Si no hay, deja None.
      - Si empresa_id en sesión no existe o no está activa: limpia empresa/sucursal.
      - Si no hay sucursal_id o no pertenece a la empresa activa: fija la primera sucursal.
      - Si la empresa no tiene sucursales: sucursal_activa = None (la UI debe avisar).
    """

    def process_request(self, request):
        request.empresa_activa = None
        request.sucursal_activa = None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return

        ses = request.session

        # ---------- Empresa activa ----------
        empresa_id = ses.get("empresa_id")

        if not empresa_id:
            empresa = _first_empresa_for_user(user)
            if empresa:
                empresa_id = empresa.id
                ses["empresa_id"] = empresa_id

        if empresa_id:
            empresa = Empresa.objects.filter(
                pk=empresa_id, activo=True).first()
            if not empresa:
                # Empresa inválida o inactiva → limpiar y salir
                ses.pop("empresa_id", None)
                ses.pop("sucursal_id", None)
                return
            request.empresa_activa = empresa
        else:
            # Sin empresa → limpiar sucursal y salir
            ses.pop("sucursal_id", None)
            return

        # ---------- Sucursal activa ----------
        sucursal_id = ses.get("sucursal_id")
        suc_qs = Sucursal.objects.filter(empresa=request.empresa_activa)

        # Validar que la sucursal pertenezca a la empresa activa
        if sucursal_id and not suc_qs.filter(pk=sucursal_id).exists():
            sucursal_id = None
            ses.pop("sucursal_id", None)

        # Si no hay sucursal válida, fijar la primera
        if not sucursal_id:
            primera = suc_qs.order_by("id").first()
            if primera:
                sucursal_id = primera.id
                ses["sucursal_id"] = sucursal_id

        if sucursal_id:
            request.sucursal_activa = suc_qs.filter(pk=sucursal_id).first()
        # Si no hay sucursales, sucursal_activa permanece en None
