# apps/payments/views.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from apps.sales.models import Venta
from apps.payments.forms.payment import PaymentForm
from apps.payments.models import Pago
from apps.payments.services.payments import registrar_pago, OverpayNeedsConfirmation


class PaymentCreateView(LoginRequiredMixin, View):
    template_name = "payments/form.html"

    def get(self, request, venta_id):
        venta = get_object_or_404(
            Venta, pk=venta_id, empresa=request.empresa_activa)
        form = PaymentForm(empresa=request.empresa_activa)
        return render(request, self.template_name, {"form": form, "venta": venta})

    def post(self, request, venta_id):
        venta = get_object_or_404(
            Venta, pk=venta_id, empresa=request.empresa_activa)

        # ❌ No permitir pagos sobre ventas canceladas
        if venta.estado == "cancelado":
            messages.error(
                request, "No se puede registrar un pago sobre una venta cancelada.")
            return redirect("sales:detail", pk=venta.pk)

        form = PaymentForm(request.POST, empresa=request.empresa_activa)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "venta": venta})

        # ✅ Defensa extra multi-tenant (cinturón y tirantes)
        medio = form.cleaned_data["medio"]
        if medio.empresa_id != venta.empresa_id:
            messages.error(
                request, "El medio de pago no pertenece a la empresa de la venta.")
            return render(request, self.template_name, {"form": form, "venta": venta})

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
                auto_split_propina=confirmar_split,  # ← si confirmó, hacemos split
            )
            if confirmar_split and len(pagos) == 2:
                messages.success(
                    request, "Pago registrado: saldo cubierto y diferencia aplicada como propina.")
            else:
                messages.success(request, "Pago registrado correctamente.")
            return redirect("sales:detail", pk=venta.pk)

        except OverpayNeedsConfirmation as e:
            # 🔁 Re-render con datos necesarios para confirmar sin perder idempotencia
            ctx = {
                # mantiene valores ingresados (incluye idempotency_key)
                "form": form,
                "venta": venta,
                "requiere_confirmacion": True,
                "saldo_actual": e.saldo,
                "monto_ingresado": e.monto,
                "diferencia_propina": e.diferencia,
                # Sugerencia para el template: agregar un botón que haga submit con
                # <input type="hidden" name="confirmar_split" value="1">
            }
            return render(request, self.template_name, ctx)

        except Exception as exc:
            messages.error(request, f"No se pudo registrar el pago: {exc}")
            return render(request, self.template_name, {"form": form, "venta": venta})


class PaymentListView(LoginRequiredMixin, ListView):
    template_name = "payments/list.html"
    model = Pago
    context_object_name = "pagos"
    paginate_by = 20

    def get_queryset(self):
        return (
            Pago.objects
            .filter(venta__empresa=self.request.empresa_activa)
            .select_related("venta", "creado_por", "medio")
            .order_by("-creado_en")
        )
