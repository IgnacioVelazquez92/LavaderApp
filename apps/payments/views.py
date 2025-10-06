# apps/payments/views.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, View

from apps.sales.models import Venta
from apps.payments.forms.payment import PaymentForm
from apps.payments.models import Pago
from apps.payments.services.payments import registrar_pago, OverpayNeedsConfirmation

from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm
# ✅ Enforcements de Turno: import correcto
from apps.cashbox.services.guards import require_turno_abierto, TurnoInexistenteError


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

        # ✅ ENFORCEMENT: turno abierto requerido para registrar pagos
        try:
            require_turno_abierto(empresa=venta.empresa,
                                  sucursal=venta.sucursal)
        except TurnoInexistenteError:
            messages.warning(
                request,
                "Antes de registrar pagos debés abrir un turno de caja para esta sucursal.",
            )
            next_url = request.get_full_path()
            abrir_url = f"{reverse('cashbox:abrir')}?next={next_url}"
            return redirect(abrir_url)

        tip_mode = request.GET.get("propina") == "1"
        form = PaymentForm(empresa=self.empresa_activa)
        ctx = {"form": form, "venta": venta,
               "tip_mode": tip_mode, **self._ctx_flags(request)}
        return render(request, self.template_name, ctx)

    def post(self, request, venta_id):
        venta = get_object_or_404(
            Venta, pk=venta_id, empresa=self.empresa_activa)

        if venta.estado == "cancelado":
            messages.error(
                request, "No se puede registrar un pago sobre una venta cancelada.")
            return redirect("sales:detail", pk=venta.pk)

        # ✅ ENFORCEMENT: turno abierto requerido para registrar pagos
        try:
            require_turno_abierto(empresa=venta.empresa,
                                  sucursal=venta.sucursal)
        except TurnoInexistenteError:
            messages.warning(
                request,
                "Antes de registrar pagos debés abrir un turno de caja para esta sucursal.",
            )
            next_url = request.get_full_path()
            abrir_url = f"{reverse('cashbox:abrir')}?next={next_url}"
            return redirect(abrir_url)

        form = PaymentForm(request.POST, empresa=self.empresa_activa)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "venta": venta, **self._ctx_flags(request)},
            )

        medio = form.cleaned_data["medio"]
        if medio.empresa_id != venta.empresa_id:
            messages.error(
                request, "El medio de pago no pertenece a la empresa de la venta.")
            return render(
                request,
                self.template_name,
                {"form": form, "venta": venta, **self._ctx_flags(request)},
            )

        confirmar_split = request.POST.get("confirmar_split") == "1"
        es_propina_pura = confirmar_split and (venta.saldo_pendiente == 0)
        usar_split = confirmar_split and (venta.saldo_pendiente > 0)

        try:
            pagos = registrar_pago(
                venta=venta,
                medio=medio,
                monto=form.cleaned_data["monto"],
                es_propina=es_propina_pura,      # True solo en propina pura
                referencia=form.cleaned_data.get("referencia") or "",
                notas=form.cleaned_data.get("notas") or "",
                creado_por=request.user,
                idempotency_key=None,
                auto_split_propina=usar_split,   # split solo si hay saldo>0
            )

            if es_propina_pura:
                messages.success(request, "Propina registrada correctamente.")
            elif usar_split and len(pagos) == 2:
                messages.success(
                    request,
                    "Pago registrado: saldo cubierto y diferencia aplicada como propina.",
                )
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
            return render(
                request,
                self.template_name,
                {"form": form, "venta": venta, **self._ctx_flags(request)},
            )


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
        ctx["puede_crear"] = self.has_perm(Perm.PAYMENTS_CREATE)
        ctx["puede_configurar"] = self.has_perm(Perm.PAYMENTS_CONFIG)
        return ctx

    def has_perm(self, perm: Perm) -> bool:
        from apps.org.permissions import has_empresa_perm
        return has_empresa_perm(self.request.user, self.empresa_activa, perm)
