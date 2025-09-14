# apps/payments/views_medios.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, View

from apps.payments.models import MedioPago
from apps.payments.forms.medio_pago import MedioPagoForm


class MedioPagoListView(ListView):
    """
    Lista de medios de pago de la empresa activa.
    """
    template_name = "payments/medios_list.html"
    context_object_name = "medios"
    paginate_by = 20

    def get_queryset(self):
        return MedioPago.objects.filter(empresa=self.request.empresa_activa).order_by("nombre")


class MedioPagoCreateView(CreateView):
    """
    Alta de medio de pago.
    """
    template_name = "payments/medios_form.html"
    form_class = MedioPagoForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.request.empresa_activa
        return kwargs

    def form_valid(self, form):
        medio: MedioPago = form.save(commit=False)
        medio.empresa = self.request.empresa_activa
        medio.save()
        messages.success(self.request, _("Medio de pago creado."))
        return redirect(reverse("payments:medios_list"))


class MedioPagoUpdateView(UpdateView):
    """
    Edición de medio de pago.
    """
    template_name = "payments/medios_form.html"
    form_class = MedioPagoForm

    def get_object(self):
        return get_object_or_404(
            MedioPago, pk=self.kwargs["pk"], empresa=self.request.empresa_activa
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.request.empresa_activa
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Cambios guardados."))
        return redirect(reverse("payments:medios_list"))


class MedioPagoToggleActivoView(View):
    """
    Activar/Desactivar medio de pago (POST).
    """

    def post(self, request, pk):
        medio = get_object_or_404(
            MedioPago, pk=pk, empresa=request.empresa_activa)
        medio.activo = not medio.activo
        medio.save(update_fields=["activo"])
        messages.success(
            request,
            _("Medio de pago {estado}.").format(
                estado=_("activado") if medio.activo else _("desactivado"))
        )
        return redirect(reverse("payments:medios_list"))
