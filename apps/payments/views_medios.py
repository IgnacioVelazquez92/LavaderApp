# apps/payments/views_medios.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, View

from apps.payments.models import MedioPago
from apps.payments.forms.medio_pago import MedioPagoForm

# 🔐 Permisos / Tenancy
from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm


class _PermCtxMixin:
    """
    Mixin auxiliar para inyectar flags de permisos en el contexto.
    Evita repetir `puede_configurar` en cada vista.
    """

    def _ctx_flags(self, request):
        return {
            "puede_configurar": has_empresa_perm(
                request.user, self.empresa_activa, Perm.PAYMENTS_CONFIG
            ),
        }


class MedioPagoListView(EmpresaPermRequiredMixin, ListView, _PermCtxMixin):
    """
    Lista de medios de pago de la empresa activa. (ADMIN: configuración)
    """
    template_name = "payments/medios_list.html"
    context_object_name = "medios"
    paginate_by = 20
    required_perms = (Perm.PAYMENTS_CONFIG,)

    def get_queryset(self):
        return (
            MedioPago.objects
            .filter(empresa=self.empresa_activa)
            .order_by("nombre")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self._ctx_flags(self.request))
        return ctx


class MedioPagoCreateView(EmpresaPermRequiredMixin, CreateView, _PermCtxMixin):
    """
    Alta de medio de pago. (ADMIN)
    """
    template_name = "payments/medios_form.html"
    form_class = MedioPagoForm
    required_perms = (Perm.PAYMENTS_CONFIG,)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        return kwargs

    def form_valid(self, form):
        medio: MedioPago = form.save(commit=False)
        medio.empresa = self.empresa_activa
        medio.save()
        messages.success(self.request, _("Medio de pago creado."))
        return redirect(reverse("payments:medios_list"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self._ctx_flags(self.request))
        return ctx


class MedioPagoUpdateView(EmpresaPermRequiredMixin, UpdateView, _PermCtxMixin):
    """
    Edición de medio de pago. (ADMIN)
    """
    template_name = "payments/medios_form.html"
    form_class = MedioPagoForm
    required_perms = (Perm.PAYMENTS_CONFIG,)

    def get_object(self):
        return get_object_or_404(
            MedioPago, pk=self.kwargs["pk"], empresa=self.empresa_activa
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Cambios guardados."))
        return redirect(reverse("payments:medios_list"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self._ctx_flags(self.request))
        return ctx


class MedioPagoToggleActivoView(EmpresaPermRequiredMixin, View):
    """
    Activar/Desactivar medio de pago (POST). (ADMIN)
    """
    required_perms = (Perm.PAYMENTS_CONFIG,)

    def post(self, request, pk):
        medio = get_object_or_404(
            MedioPago, pk=pk, empresa=self.empresa_activa
        )
        medio.activo = not medio.activo
        medio.save(update_fields=["activo"])
        messages.success(
            request,
            _("Medio de pago {estado}.").format(
                estado=_("activado") if medio.activo else _("desactivado")
            ),
        )
        return redirect(reverse("payments:medios_list"))
