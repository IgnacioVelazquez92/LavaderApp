# apps/payments/views.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, View

from apps.sales.models import Venta
from apps.payments.forms.payment import PaymentForm
from apps.payments.models import Pago
from apps.payments.services.payments import registrar_pago, OverpayNeedsConfirmation

# apps/payments/views.py
from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm


class PaymentCreateView(EmpresaPermRequiredMixin, View):
    template_name = "payments/form.html"
    required_perms = (Perm.PAYMENTS_CREATE,)

    def _ctx_flags(self, request):
        return {
            "puede_crear": has_empresa_perm(request.user, self.empresa_activa, Perm.PAYMENTS_CREATE),
            "puede_configurar": has_empresa_perm(request.user, self.empresa_activa, Perm.PAYMENTS_CONFIG),
        }

    def get(self, request, venta_id):
        venta = get_object_or_404(
            Venta, pk=venta_id, empresa=self.empresa_activa)
        form = PaymentForm(empresa=self.empresa_activa)
        ctx = {"form": form, "venta": venta, **self._ctx_flags(request)}
        return render(request, self.template_name, ctx)

    def post(self, request, venta_id):
        venta = get_object_or_404(
            Venta, pk=venta_id, empresa=self.empresa_activa)

        if venta.estado == "cancelado":
            messages.error(
                request, "No se puede registrar un pago sobre una venta cancelada.")
            return redirect("sales:detail", pk=venta.pk)

        form = PaymentForm(request.POST, empresa=self.empresa_activa)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "venta": venta, **self._ctx_flags(request)})

        medio = form.cleaned_data["medio"]
        if medio.empresa_id != venta.empresa_id:
            messages.error(
                request, "El medio de pago no pertenece a la empresa de la venta.")
            return render(request, self.template_name, {"form": form, "venta": venta, **self._ctx_flags(request)})

        confirmar_split = request.POST.get("confirmar_split") == "1"

        try:
            pagos = registrar_pago(
                venta=venta,
                medio=medio,
                monto=form.cleaned_data["monto"],
                es_propina=form.cleaned_data.get("es_propina", False),
                referencia=form.cleaned_data.get("referencia") or "",
                notas=form.cleaned_data.get("notas") or "",
                creado_por=request.user,
                idempotency_key=form.cleaned_data.get("idempotency_key"),
                auto_split_propina=confirmar_split,
            )
            if confirmar_split and len(pagos) == 2:
                messages.success(
                    request, "Pago registrado: saldo cubierto y diferencia aplicada como propina.")
            else:
                messages.success(request, "Pago registrado correctamente.")
            return redirect("sales:detail", pk=venta.pk)

        except OverpayNeedsConfirmation as e:
            ctx = {
                "form": form,
                "venta": venta,
                "requiere_confirmacion": True,
                "saldo_actual": e.saldo,
                "monto_ingresado": e.monto,
                "diferencia_propina": e.diferencia,
                **self._ctx_flags(request),
            }
            return render(request, self.template_name, ctx)

        except Exception as exc:
            messages.error(request, f"No se pudo registrar el pago: {exc}")
            return render(request, self.template_name, {"form": form, "venta": venta, **self._ctx_flags(request)})


class PaymentListView(EmpresaPermRequiredMixin, ListView):
    template_name = "payments/list.html"
    model = Pago
    context_object_name = "pagos"
    paginate_by = 20
    required_perms = (Perm.PAYMENTS_VIEW,)

    def get_queryset(self):
        return (
            Pago.objects.filter(venta__empresa=self.empresa_activa)
            .select_related("venta", "creado_por", "medio")
            .order_by("-creado_en")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Flags de permisos para mostrar/ocultar botones en template
        ctx["puede_crear"] = self.has_perm(Perm.PAYMENTS_CREATE)
        ctx["puede_configurar"] = self.has_perm(Perm.PAYMENTS_CONFIG)
        return ctx

    def has_perm(self, perm: Perm) -> bool:
        from apps.org.permissions import has_empresa_perm
        return has_empresa_perm(self.request.user, self.empresa_activa, perm)
