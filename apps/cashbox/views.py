# apps/cashbox/views.py
from __future__ import annotations
from apps.cashbox.services.totals import cierre_z_totales_dia
from django.views.generic import TemplateView

from datetime import datetime
from typing import Optional

from django.contrib import messages
from django.db.models import Sum, F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import DetailView, FormView, ListView, View

from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm
from apps.cashbox.models import TurnoCaja
from apps.cashbox.services.cashbox import abrir_turno, cerrar_turno
from apps.cashbox.services.guards import get_turno_abierto
from apps.cashbox.forms import OpenCashboxForm, CloseCashboxForm
from apps.payments.models import Pago
from apps.cashbox.services.totals import preview_totales_turno


def _parse_date_range(request) -> tuple[Optional[datetime], Optional[datetime]]:
    def _p(name: str) -> Optional[datetime]:
        val = request.GET.get(name)
        if not val:
            return None
        d = parse_date(val)
        if not d:
            return None
        if name == "desde":
            return timezone.make_aware(datetime(d.year, d.month, d.day, 0, 0, 0))
        return timezone.make_aware(datetime(d.year, d.month, d.day, 23, 59, 59))

    return _p("desde"), _p("hasta")


# --- Reemplazar SOLO esta función ---

def _preview_totales_turno(turno: TurnoCaja) -> list[dict]:
    desde, hasta = turno.rango()
    qs = (
        Pago.objects.filter(
            turno=turno, creado_en__gte=desde, creado_en__lte=hasta)
        .select_related("medio")
        # ⬇️ sin alias "es_propina=F('es_propina')" (eso rompe)
        .values("medio__nombre", "es_propina")
        .annotate(total=Sum("monto"))
    )

    acc: dict[str, dict] = {}
    for row in qs:
        medio = row.get("medio__nombre") or "—"
        is_tip = bool(row.get("es_propina"))
        total = row.get("total") or 0
        acc.setdefault(medio, {"medio": medio, "monto": 0, "propinas": 0})
        if is_tip:
            acc[medio]["propinas"] += total
        else:
            acc[medio]["monto"] += total

    return sorted(acc.values(), key=lambda r: r["medio"])


class TurnoListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (Perm.PAYMENTS_VIEW,)
    model = TurnoCaja
    template_name = "cashbox/list.html"
    context_object_name = "turnos"
    paginate_by = 20

    def get_queryset(self):
        empresa = self.empresa_activa
        qs = TurnoCaja.objects.filter(empresa=empresa).select_related(
            "sucursal", "abierto_por", "cerrado_por"
        )

        sucursal_id = self.request.GET.get("sucursal")
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)

        desde, hasta = _parse_date_range(self.request)
        if desde:
            qs = qs.filter(abierto_en__gte=desde)
        if hasta:
            qs = qs.filter(abierto_en__lte=hasta)

        abiertos = self.request.GET.get("abiertos")
        if abiertos == "1":
            qs = qs.filter(cerrado_en__isnull=True)
        elif abiertos == "0":
            qs = qs.filter(cerrado_en__isnull=False)

        return qs.order_by("-abierto_en")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        suc = getattr(self.request, "sucursal_activa", None)
        ctx["sucursales"] = emp.sucursales.all() if emp else []
        ctx["sucursal_filtro"] = self.request.GET.get("sucursal") or ""
        ctx["desde"] = self.request.GET.get("desde") or ""
        ctx["hasta"] = self.request.GET.get("hasta") or ""
        ctx["abiertos"] = self.request.GET.get("abiertos") or ""
        # turno abierto actual de la sucursal activa (para CTA de cabecera)
        from apps.cashbox.services.guards import get_turno_abierto
        ctx["turno_abierto"] = get_turno_abierto(
            emp, suc) if (emp and suc) else None
        return ctx


class TurnoOpenView(EmpresaPermRequiredMixin, FormView):
    required_perms = (Perm.PAYMENTS_CREATE,)
    form_class = OpenCashboxForm
    template_name = "cashbox/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accion"] = "abrir"
        ctx["sucursal"] = getattr(self.request, "sucursal_activa", None)
        return ctx

    def form_valid(self, form: OpenCashboxForm):
        empresa = self.empresa_activa
        sucursal = getattr(self.request, "sucursal_activa", None)

        if not sucursal:
            messages.error(
                self.request, "Debés seleccionar una sucursal activa para abrir turno.")
            return redirect("org:selector")

        existente = get_turno_abierto(empresa, sucursal)
        if existente:
            messages.warning(
                self.request, "Ya existe un turno abierto en esta sucursal.")
            next_url = self.request.GET.get("next")
            return redirect(next_url or reverse("cashbox:detalle", kwargs={"id": str(existente.id)}))

        turno = abrir_turno(
            empresa=empresa,
            sucursal=sucursal,
            user=self.request.user,
            responsable_nombre=form.cleaned_data.get(
                "responsable_nombre", "").strip(),
            observaciones=form.cleaned_data.get("observaciones", "").strip(),
        )
        messages.success(self.request, "Turno abierto correctamente.")
        next_url = self.request.GET.get("next")
        return redirect(next_url or reverse("cashbox:detalle", kwargs={"id": str(turno.id)}))


class TurnoCloseView(EmpresaPermRequiredMixin, FormView):
    required_perms = (Perm.PAYMENTS_CREATE,)
    form_class = CloseCashboxForm
    template_name = "cashbox/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.turno = get_object_or_404(
            TurnoCaja, id=kwargs.get("id"), empresa=self.empresa_activa
        )
        if not self.turno.esta_abierto:
            messages.info(request, "Este turno ya está cerrado.")
            return redirect(reverse("cashbox:detalle", kwargs={"id": str(self.turno.id)}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accion"] = "cerrar"
        ctx["turno"] = self.turno
        ctx["preview_totales"] = preview_totales_turno(turno=self.turno)
        return ctx

    def form_valid(self, form: CloseCashboxForm):
        try:
            contado = form.cleaned_data.get("monto_contado_total")
            # ⬇️ guardar el resultado
            res = cerrar_turno(
                turno=self.turno,
                user=self.request.user,
                monto_contado_total=contado,
            )
            messages.success(self.request, "Turno cerrado correctamente.")
            # ⬇️ usar el turno dentro del resultado
            return redirect(reverse("cashbox:detalle", kwargs={"id": str(res.turno.id)}))
        except Exception as e:
            messages.error(
                self.request, f"No fue posible cerrar el turno: {e}")
            return redirect(reverse("cashbox:detalle", kwargs={"id": str(self.turno.id)}))


class TurnoDetailView(EmpresaPermRequiredMixin, DetailView):
    required_perms = (Perm.PAYMENTS_VIEW,)
    template_name = "cashbox/detail.html"
    pk_url_kwarg = "id"
    context_object_name = "turno"
    model = TurnoCaja

    def get_object(self, queryset=None):
        return get_object_or_404(
            TurnoCaja.objects.select_related(
                "empresa", "sucursal", "abierto_por", "cerrado_por"),
            id=self.kwargs.get("id"),
            empresa=self.empresa_activa,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        turno: TurnoCaja = ctx["turno"]
        ctx["preview_totales"] = _preview_totales_turno(turno)
        emp = self.empresa_activa
        ctx["puede_cerrar"] = turno.esta_abierto and has_empresa_perm(
            self.request.user, emp, Perm.PAYMENTS_CREATE)
        return ctx


# --- Cierre Z (resumen diario por método, sin depender de turnos) ---------


class CierreZView(EmpresaPermRequiredMixin, TemplateView):
    """
    Muestra totales del día (Cierre Z) por método de pago, separando monto (sin propina) y propinas.
    Filtros opcionales por fecha (?fecha=YYYY-MM-DD) y sucursal (?sucursal=<id>).
    """
    required_perms = (Perm.PAYMENTS_VIEW,
                      )  # podés crear un Perm específico luego
    template_name = "cashbox/z.html"

    def get_context_data(self, **kwargs):
        from apps.org.models import Sucursal

        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa_activa

        # --- filtros ---
        fecha_str = self.request.GET.get("fecha") or ""
        fecha = parse_date(fecha_str) or timezone.localdate()

        sucursal = None
        sucursal_id = self.request.GET.get("sucursal")
        if sucursal_id:
            # seguridad de tenant
            sucursal = get_object_or_404(
                Sucursal, id=sucursal_id, empresa=empresa)

        # --- datos ---
        totales = cierre_z_totales_dia(
            empresa=empresa, sucursal=sucursal, fecha=fecha)

        total_monto = sum(t.monto for t in totales)
        total_prop = sum(t.propinas for t in totales)
        total_gral = total_monto + total_prop

        # --- contexto ---
        ctx.update(
            {
                "fecha": fecha,
                "fecha_str": fecha.strftime("%Y-%m-%d"),
                "sucursal_sel": sucursal,
                "sucursales": list(empresa.sucursales.all()) if empresa else [],
                "totales": totales,
                "total_monto": total_monto,
                "total_propinas": total_prop,
                "total_general": total_gral,
            }
        )
        return ctx
