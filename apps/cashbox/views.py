# apps/cashbox/views.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.views.generic import DetailView, FormView, ListView, View

from apps.cashbox.forms import CloseCashboxForm, OpenCashboxForm
from apps.cashbox.models import CierreCaja
from apps.cashbox import selectors
from apps.cashbox.services import cashbox as cashbox_services
from apps.cashbox.services.cashbox import (
    CierreAbiertoExistenteError,
    CierreNoAbiertoError,
)
from apps.cashbox.services.totals import TotalesMetodo


# -------------------------
# Helpers / Permisos básicos
# -------------------------

class TenancyRequiredMixin(LoginRequiredMixin):
    """
    Requiere empresa y sucursal activas en la sesión (inyectadas por el TenancyMiddleware).
    """

    def dispatch(self, request, *args, **kwargs):
        empresa = getattr(request, "empresa_activa", None)
        sucursal = getattr(request, "sucursal_activa", None)

        if empresa is None:
            messages.error(request, "Debés seleccionar un lavadero activo.")
            # En muchos flujos el selector de empresa/sucursal vive en /org/seleccionar/
            return redirect(reverse("org:selector"))

        # Para **abrir/cerrar** caja pedimos sucursal activa.
        if self.requires_branch() and sucursal is None:
            messages.error(
                request, "Debés seleccionar una sucursal activa para operar la caja.")
            return redirect(reverse("org:selector"))

        return super().dispatch(request, *args, **kwargs)

    def requires_branch(self) -> bool:
        """Por defecto, todas las vistas de cashbox requieren sucursal activa."""
        return True


class CashboxPermissionMixin(TenancyRequiredMixin):
    """
    Verificación suave de rol. Intenta usar helpers de `apps.accounts.permissions`
    si están disponibles; si no, deja pasar a usuarios autenticados (MVP).
    Roles esperados: admin / operador.
    """

    allowed_roles = {"admin", "operador"}

    def dispatch(self, request, *args, **kwargs):
        # Ya validó TenancyRequiredMixin
        try:
            from apps.accounts.permissions import user_has_role  # type: ignore
        except Exception:
            return super().dispatch(request, *args, **kwargs)

        empresa = request.empresa_activa
        if not user_has_role(request.user, empresa, roles=self.allowed_roles):
            raise PermissionDenied("No tenés permisos para operar la caja.")
        return super().dispatch(request, *args, **kwargs)


# -------------------------
# Vistas
# -------------------------

class CashboxListView(CashboxPermissionMixin, ListView):
    """
    Listado de cierres por empresa (filtrable por sucursal, rango y estado).
    GET params:
      - sucursal: id (opcional; si no se envía, trae todas las de la empresa)
      - desde / hasta: YYYY-MM-DD (filtran por `abierto_en`)
      - abiertos: "1" (solo abiertos) | "0" (solo cerrados)
    """
    model = CierreCaja
    template_name = "cashbox/list.html"
    context_object_name = "cierres"
    paginate_by = 20

    def get_queryset(self):
        empresa = self.request.empresa_activa
        sucursal = None
        if self.request.GET.get("sucursal"):
            # Seguridad: no asumimos acceso si no pertenece a la empresa
            from apps.org.models import Sucursal
            sucursal = get_object_or_404(
                Sucursal, id=self.request.GET["sucursal"], empresa=empresa)

        def _parse_date(name: str) -> Optional[datetime]:
            val = self.request.GET.get(name)
            if not val:
                return None
            # YYYY-MM-DD → inicio/fin del día según convenga
            try:
                d = parse_date(val)
                if not d:
                    return None
                # Usamos comienzo/fin del día para incluir todo el rango
                if name == "desde":
                    return timezone.make_aware(datetime(d.year, d.month, d.day, 0, 0, 0))
                return timezone.make_aware(datetime(d.year, d.month, d.day, 23, 59, 59))
            except Exception:
                return None

        desde = _parse_date("desde")
        hasta = _parse_date("hasta")
        abiertos = self.request.GET.get("abiertos")
        if abiertos == "1":
            abiertos = True
        elif abiertos == "0":
            abiertos = False
        else:
            abiertos = None

        return selectors.cierres_por_fecha(
            empresa=empresa, sucursal=sucursal, desde=desde, hasta=hasta, abiertos=abiertos
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sucursal_filtro"] = self.request.GET.get("sucursal") or ""
        ctx["desde"] = self.request.GET.get("desde") or ""
        ctx["hasta"] = self.request.GET.get("hasta") or ""
        ctx["abiertos"] = self.request.GET.get("abiertos") or ""
        return ctx


class CashboxOpenView(CashboxPermissionMixin, FormView):
    """
    Apertura de cierre de caja para la sucursal activa.
    """
    form_class = OpenCashboxForm
    template_name = "cashbox/form.html"

    def form_valid(self, form: OpenCashboxForm):
        empresa = self.request.empresa_activa
        sucursal = self.request.sucursal_activa
        try:
            result = cashbox_services.abrir_cierre(
                empresa=empresa,
                sucursal=sucursal,
                usuario=self.request.user,
                abierto_en=form.cleaned_data.get("abierto_en"),
                notas=form.cleaned_data.get("notas") or "",
            )
            messages.success(self.request, "Caja abierta correctamente.")
            return redirect(reverse("cashbox:detail", kwargs={"id": str(result.cierre.id)}))
        except CierreAbiertoExistenteError:
            # Si ya hay una abierta, redirigimos a esa
            existente = selectors.get_cierre_abierto(
                empresa=empresa, sucursal=sucursal)
            messages.warning(
                self.request, "Ya existe un cierre abierto en esta sucursal.")
            if existente:
                return redirect(reverse("cashbox:detail", kwargs={"id": str(existente.id)}))
            # Fallback si no lo encontramos
            return redirect(reverse("cashbox:list"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accion"] = "abrir"
        ctx["sucursal"] = self.request.sucursal_activa
        return ctx


class CashboxCloseView(CashboxPermissionMixin, FormView):
    """
    Cierre de un CierreCaja abierto. Muestra **preview** de totales y al confirmar
    persiste los `CierreCajaTotal` y sella `cerrado_en`.
    """
    form_class = CloseCashboxForm
    template_name = "cashbox/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.cierre = get_object_or_404(
            CierreCaja, id=kwargs.get("id"), empresa=request.empresa_activa
        )
        if not self.cierre.esta_abierta:
            messages.info(request, "Este cierre ya está cerrado.")
            return redirect(reverse("cashbox:detail", kwargs={"id": str(self.cierre.id)}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accion"] = "cerrar"
        ctx["cierre"] = self.cierre
        # Preview de totales hasta ahora (o hasta lo que el usuario elija luego)
        ctx["preview_totales"] = cashbox_services.preview_totales_actuales(
            cierre=self.cierre)
        return ctx

    def form_valid(self, form: CloseCashboxForm):
        try:
            cerrado_en = form.cleaned_data.get("cerrado_en") or timezone.now()
            res = cashbox_services.cerrar_cierre(
                cierre=self.cierre,
                actor=self.request.user,
                cerrado_en=cerrado_en,
                notas_append=form.cleaned_data.get("notas_append") or None,
                recalcular_y_guardar_totales=True,
            )
            messages.success(self.request, "Cierre realizado correctamente.")
            return redirect(reverse("cashbox:detail", kwargs={"id": str(res.cierre.id)}))
        except CierreNoAbiertoError:
            messages.error(self.request, "El cierre ya se encontraba cerrado.")
            return redirect(reverse("cashbox:detail", kwargs={"id": str(self.cierre.id)}))
        except Exception as e:
            messages.error(self.request, f"No fue posible cerrar la caja: {e}")
            return redirect(reverse("cashbox:detail", kwargs={"id": str(self.cierre.id)}))


class CashboxDetailView(CashboxPermissionMixin, DetailView):
    """
    Detalle del cierre con desglose por método.
    Si el cierre está **abierto**, muestra también un **preview** de totales al momento.
    """
    template_name = "cashbox/detail.html"
    pk_url_kwarg = "id"
    context_object_name = "cierre"
    model = CierreCaja

    def get_object(self, queryset=None):
        return get_object_or_404(
            CierreCaja.objects.select_related(
                "empresa", "sucursal", "usuario", "cerrado_por"),
            id=self.kwargs.get("id"),
            empresa=self.request.empresa_activa,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cierre: CierreCaja = ctx["cierre"]
        # Totales persistidos (si ya fue cerrado) o al menos los existentes
        ctx["totales"] = selectors.totales_de_cierre(cierre=cierre)
        # Preview en vivo si está abierto
        ctx["preview_totales"] = None
        if cierre.esta_abierta:
            ctx["preview_totales"] = cashbox_services.preview_totales_actuales(
                cierre=cierre)
        return ctx
