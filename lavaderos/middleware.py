# lavaderos/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.db.models import Exists, OuterRef

from apps.org.models import Empresa, Sucursal


class TenancyMiddleware(MiddlewareMixin):
    """
    Inyecta en cada request autenticado:
      - request.empresa_activa: Empresa o None
      - request.sucursal_activa: Sucursal o None (de la empresa_activa)

    Reglas:
      - Si no hay empresa_id en sesión, fija la primera empresa del usuario (membership) que esté activa.
      - Si empresa_id apunta a una empresa inexistente o inactiva, limpia empresa_id/sucursal_id.
      - Si no hay sucursal_id en sesión (o no pertenece a la empresa activa), fija la primera sucursal de esa empresa.
      - Si la empresa no tiene sucursales, sucursal_activa queda en None (la UI debe avisar y ofrecer crear).
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
            # Primera empresa ACTIVA donde el usuario tenga membership
            # (evita import circular con accounts usando un Exists)
            empresa = (
                Empresa.objects.filter(activo=True)
                .annotate(
                    is_member=Exists(
                        # asumiendo modelo membership apps.accounts.EmpresaMembership(user, empresa)
                        user.empresamembership_set.filter(
                            empresa=OuterRef("pk"))
                    )
                )
                .filter(is_member=True)
                .order_by("id")
                .first()
            )
            if empresa:
                empresa_id = empresa.id
                ses["empresa_id"] = empresa_id

        if empresa_id:
            empresa = Empresa.objects.filter(
                pk=empresa_id, activo=True).first()
            if not empresa:
                # Empresa inválida: limpiar y salir (sin empresa/sucursal activas)
                ses.pop("empresa_id", None)
                ses.pop("sucursal_id", None)
                return
            request.empresa_activa = empresa
        else:
            # Sin empresa → nada más que hacer
            ses.pop("sucursal_id", None)
            return

        # ---------- Sucursal activa ----------
        sucursal_id = ses.get("sucursal_id")
        suc_qs = Sucursal.objects.filter(empresa=request.empresa_activa)

        # Validar que la sucursal en sesión pertenezca a la empresa activa
        if sucursal_id and not suc_qs.filter(pk=sucursal_id).exists():
            sucursal_id = None
            ses.pop("sucursal_id", None)

        # Si no hay sucursal válida en sesión, fijar la primera de la empresa
        if not sucursal_id:
            primera = suc_qs.order_by("id").first()
            if primera:
                sucursal_id = primera.id
                ses["sucursal_id"] = sucursal_id

        if sucursal_id:
            request.sucursal_activa = suc_qs.filter(pk=sucursal_id).first()
        # Si la empresa no tiene sucursales, request.sucursal_activa queda en None (UI debe manejarlo)
