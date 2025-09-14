# apps/payments/views.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView

from apps.sales.models import Venta
from apps.payments.forms.payment import PaymentForm
from apps.payments.services import payments as payment_services
from apps.payments.models import Pago


class PaymentCreateView(FormView):
    template_name = "payments/form.html"
    form_class = PaymentForm

    def dispatch(self, request, *args, **kwargs):
        # Venta dentro de la empresa activa (tenancy)
        self.venta = get_object_or_404(
            Venta,
            id=kwargs.get("venta_id"),
            empresa=request.empresa_activa,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pasar empresa al form para filtrar medios activos
        kwargs["empresa"] = self.request.empresa_activa
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["venta"] = self.venta
        return ctx

    def form_valid(self, form):
        try:
            payment_services.registrar_pago(
                venta=self.venta,
                medio=form.cleaned_data["medio"],
                monto=form.cleaned_data["monto"],
                es_propina=form.cleaned_data.get("es_propina", False),
                referencia=form.cleaned_data.get("referencia"),
                notas=form.cleaned_data.get("notas"),
                creado_por=self.request.user,
            )
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

        messages.success(self.request, _("Pago registrado con éxito."))
        return redirect(reverse("sales:detail", args=[self.venta.id]))


class PaymentListView(ListView):
    template_name = "payments/list.html"
    model = Pago
    context_object_name = "pagos"
    paginate_by = 20

    def get_queryset(self):
        return (
            Pago.objects.filter(venta__empresa=self.request.empresa_activa)
            .select_related("venta", "creado_por", "medio")
            .order_by("-creado_en")
        )
