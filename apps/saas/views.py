# apps/saas/views.py
"""
Vistas server-rendered del módulo SaaS.

Objetivos (MVP):
- Panel de empresa: muestra plan vigente, estado y uso de límites.
- Catálogo público de planes para usuarios autenticados (no staff).
- Acción POST de "Solicitar upgrade" (MVP: deja mensaje y redirige).

NOTA: El CRUD real de Planes/Suscripciones queda en Django Admin (staff).
"""

# apps/saas/views.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView, ListView

from .models import PlanSaaS, SuscripcionSaaS
from .selectors import planes_activos, suscripcion_snapshot, suscripcion_de
from .limits import get_usage_snapshot
from .services.subscriptions import recompute_estado

# ---------------------------
# Mixins de acceso
# ---------------------------


class EmpresaContextRequiredMixin(LoginRequiredMixin):
    """
    Requiere usuario autenticado y contexto de empresa activa.
    El panel es informativo; no consulta permisos finos aquí.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request, "empresa_activa", None):
            messages.warning(request, _(
                "Primero debés seleccionar o crear un lavadero."))
            return redirect("org:selector")
        return super().dispatch(request, *args, **kwargs)
# ---------------------------
# Panel de Empresa
# ---------------------------


class SaaSPanelView(EmpresaContextRequiredMixin, TemplateView):
    template_name = "saas/panel.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        empresa = self.request.empresa_activa
        sucursal = getattr(self.request, "sucursal_activa", None)

        # Recalcular estado SOLO si hay suscripción
        sub = suscripcion_de(empresa)
        if sub:
            recompute_estado(empresa=empresa)

        ctx["snapshot"] = suscripcion_snapshot(empresa)
        ctx["usage"] = get_usage_snapshot(empresa, sucursal=sucursal)
        return ctx

# ---------------------------
# Catálogo público de planes (para usuarios autenticados)
# ---------------------------


class PlanesPublicListView(LoginRequiredMixin, ListView):
    """
    Lista de planes visibles para cualquier usuario autenticado.
    La vista inyecta current_plan_id para que el template NO acceda a .suscripcion directo.
    """
    template_name = "saas/planes_public.html"
    context_object_name = "planes"

    def get_queryset(self):
        return planes_activos()

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        empresa = getattr(self.request, "empresa_activa", None)
        current_plan_id: Optional[str] = None
        if empresa:
            try:
                # puede lanzar RelatedObjectDoesNotExist
                sub: SuscripcionSaaS = empresa.suscripcion
                current_plan_id = str(sub.plan_id)
            except Exception:
                current_plan_id = None
        ctx["current_plan_id"] = current_plan_id
        return ctx


class SolicitarUpgradeView(EmpresaContextRequiredMixin, View):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        plan_id = request.POST.get("plan_id")
        plan = get_object_or_404(PlanSaaS, id=plan_id, activo=True)
        messages.success(
            request,
            _("¡Listo! Registramos tu interés en el plan %(plan)s. Pronto habilitaremos el proceso de upgrade.")
            % {"plan": plan.nombre}
        )
        return redirect(reverse("saas:planes_public"))
