from apps.org.models import Empresa, Sucursal
from django.utils.deprecation import MiddlewareMixin


class TenancyMiddleware(MiddlewareMixin):
    """
    - Inyecta request.empresa_activa (objeto Empresa o None) en cada request autenticado.
    - (Opcional) Podés forzar que ciertas rutas requieran empresa activa.
    """

    def process_request(self, request):
        request.empresa_activa = None
        request.sucursal_activa = None

        if not request.user.is_authenticated:
            return

        # Empresa activa
        eid = request.session.get("empresa_id")
        if not eid:
            # Default a primera empresa si existe
            from apps.org.views import _first_empresa_for
            emp = _first_empresa_for(request.user)
            if emp:
                request.session["empresa_id"] = emp.pk
                eid = emp.pk

        if eid:
            try:
                request.empresa_activa = Empresa.objects.get(
                    pk=eid, activo=True)
            except Empresa.DoesNotExist:
                request.session.pop("empresa_id", None)
                request.session.pop("sucursal_id", None)
                return

        # Sucursal activa (si hay empresa)
        sid = request.session.get("sucursal_id")
        if sid and request.empresa_activa:
            try:
                request.sucursal_activa = Sucursal.objects.get(
                    pk=sid, empresa=request.empresa_activa)
            except Sucursal.DoesNotExist:
                request.session.pop("sucursal_id", None)
