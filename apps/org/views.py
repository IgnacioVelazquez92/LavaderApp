from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render, get_object_or_404
from django.views import View
from .models import Empresa
from .selectors import empresas_para_usuario


class SelectorEmpresaView(LoginRequiredMixin, View):
    template_name = "org/selector.html"

    def get(self, request):
        empresas = empresas_para_usuario(request.user)
        # Si viene ?empresa=<id> en query, intentamos activar directo
        empresa_id = request.GET.get("empresa")
        if empresa_id:
            return self._activar_y_redirigir(request, empresa_id)
        return render(request, self.template_name, {"empresas": empresas})

    def post(self, request):
        empresa_id = request.POST.get("empresa")
        if not empresa_id:
            messages.error(request, "Debes seleccionar una empresa.")
            return redirect("org_selector")
        return self._activar_y_redirigir(request, empresa_id)

    def _activar_y_redirigir(self, request, empresa_id):
        # Validar que existe la empresa y que el usuario es miembro
        empresa = get_object_or_404(Empresa, pk=empresa_id, activo=True)

        # Comprobamos membresía del usuario
        # import local para evitar ciclo
        from apps.accounts.models import EmpresaMembership
        es_miembro = EmpresaMembership.objects.filter(
            user=request.user, empresa=empresa
        ).exists()

        if not es_miembro:
            messages.error(request, "No tenés acceso a esta empresa.")
            return redirect("org_selector")

        request.session["empresa_id"] = str(empresa.pk)
        messages.success(request, f"Empresa activa: {empresa.nombre}")
        # Redirección de conveniencia: home o la URL previa si la pasás por ?next=
        next_url = request.GET.get("next") or request.POST.get("next") or "/"
        return redirect(next_url)
