# apps/pricing/views.py
from __future__ import annotations
from django.utils.timezone import localdate
from dataclasses import asdict
from datetime import date
from typing import Optional
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, CreateView, UpdateView
from django.views import View
from apps.org.permissions import (
    EmpresaPermRequiredMixin,
    has_empresa_perm,
    Perm,
)

from .forms.price import PriceForm
from .models import PrecioServicio
from .selectors import listar_precios
from .services.pricing import PrecioCmd, create_or_replace, update_price


# ============================================================
# Utilidades de vistas
# ============================================================

class BackUrlMixin:
    """
    Provee soporte de retorno consistente:
    - Prioriza querystring `?next=...`
    - Fallback configurable vía `default_url_name`
    """
    default_url_name: Optional[str] = None  # e.g. "pricing:list"

    def get_success_url(self) -> str:
        nxt = self.request.POST.get("next") or self.request.GET.get("next")
        if nxt:
            return nxt
        if self.default_url_name:
            return reverse(self.default_url_name)
        # último recurso: listado de precios
        return reverse("pricing:list")


# ============================================================
# Listado
# ============================================================

class PriceListView(EmpresaPermRequiredMixin, ListView):
    """
    Listado de precios con filtros opcionales:
    - sucursal (id)
    - servicio (id)
    - tipo (id de TipoVehiculo)
    - vigentes_en (YYYY-MM-DD) → filtra por precios vigentes ese día
    - activos (true/false) → flag activo
    """
    model = PrecioServicio
    template_name = "pricing/list.html"
    context_object_name = "precios"
    paginate_by = 25
    default_url_name = "pricing:list"
    required_perms = (Perm.PRICING_VIEW,)

    @property
    def empresa(self):
        # Tenancy: provisto por middleware/contexto
        return getattr(self, "empresa_activa", None) or getattr(self.request, "empresa_activa", None)

    def get_queryset(self):
        empresa = self.empresa
        if not empresa:
            return PrecioServicio.objects.none()

        # Parseo de filtros GET
        sucursal_id = self.request.GET.get("sucursal")
        servicio_id = self.request.GET.get("servicio")
        tipo_id = self.request.GET.get("tipo")
        vigentes_en_str = self.request.GET.get("vigentes_en")
        activos_str = self.request.GET.get("activos")

        sucursal = int(
            sucursal_id) if sucursal_id and sucursal_id.isdigit() else None
        servicio = int(
            servicio_id) if servicio_id and servicio_id.isdigit() else None
        tipo = int(tipo_id) if tipo_id and tipo_id.isdigit() else None

        # Fecha
        vigentes_en: Optional[date] = None
        if vigentes_en_str:
            d = parse_date(vigentes_en_str)
            if d:
                vigentes_en = d

        # Activos
        activos: Optional[bool] = None
        if activos_str is not None:
            low = activos_str.lower()
            if low in ("1", "true", "t", "yes", "y", "si", "sí"):
                activos = True
            elif low in ("0", "false", "f", "no", "n"):
                activos = False

        qs = listar_precios(
            empresa,
            sucursal=sucursal,
            servicio=servicio,
            tipo=tipo,
            vigentes_en=vigentes_en,
            activos=activos,
        )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa
        if empresa:
            from apps.org.models import Sucursal
            from apps.catalog.models import Servicio
            from apps.vehicles.models import TipoVehiculo
            ctx["sucursales"] = Sucursal.objects.filter(
                empresa=empresa).order_by("nombre")
            ctx["servicios"] = Servicio.objects.filter(
                empresa=empresa, activo=True).order_by("nombre")
            ctx["tipos"] = TipoVehiculo.objects.filter(
                empresa=empresa, activo=True).order_by("nombre")
        else:
            ctx["sucursales"] = ctx["servicios"] = ctx["tipos"] = []

        # Mantener filtros actuales
        ctx["filters"] = {
            "sucursal": self.request.GET.get("sucursal") or "",
            "servicio": self.request.GET.get("servicio") or "",
            "tipo": self.request.GET.get("tipo") or "",
            "vigentes_en": self.request.GET.get("vigentes_en") or "",
            "activos": self.request.GET.get("activos") or "",
        }

        # === Flags UI (no seguridad; solo UX) ===
        user = self.request.user
        ctx["puede_crear"] = has_empresa_perm(
            user, empresa, Perm.PRICING_CREATE)
        ctx["puede_editar"] = has_empresa_perm(
            user, empresa, Perm.PRICING_EDIT)
        ctx["puede_eliminar"] = has_empresa_perm(
            user, empresa, Perm.PRICING_DELETE)
        ctx["puede_desactivar"] = has_empresa_perm(
            user, empresa, Perm.PRICING_DEACTIVATE)

        return ctx


# ============================================================
# Alta
# ============================================================

class PriceCreateView(EmpresaPermRequiredMixin, BackUrlMixin, CreateView):
    """
    Alta de precio. **No** persiste directamente el ModelForm, sino que delega
    la creación a `services.pricing.create_or_replace` para:
      - cerrar vigencias abiertas,
      - evitar solapamientos de forma segura,
      - respetar reglas de negocio centralizadas.
    """
    model = PrecioServicio
    form_class = PriceForm
    template_name = "pricing/form.html"
    default_url_name = "pricing:list"
    required_perms = (Perm.PRICING_CREATE,)

    @property
    def empresa(self):
        return getattr(self, "empresa_activa", None) or getattr(self.request, "empresa_activa", None)

    def get_form_kwargs(self):
        """
        Inyecta `empresa` al formulario para limitar querysets y asignar empresa en save().
        """
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form: PriceForm):
        empresa = self.empresa
        if not empresa:
            messages.error(
                self.request, "No hay una empresa activa seleccionada.")
            return self.form_invalid(form)

        cd = form.cleaned_data
        cmd = PrecioCmd(
            empresa=empresa,
            sucursal=cd["sucursal"],
            servicio=cd["servicio"],
            tipo_vehiculo=cd["tipo_vehiculo"],
            precio=cd["precio"],
            moneda=cd["moneda"],
            vigencia_inicio=cd["vigencia_inicio"] or timezone.localdate(),
            vigencia_fin=cd.get("vigencia_fin"),
            activo=cd.get("activo", True),
        )
        # Crear aplicando reglas de negocio
        obj = create_or_replace(cmd)
        messages.success(
            self.request,
            f"Precio creado: {obj.servicio} × {obj.tipo_vehiculo} @ {obj.sucursal} - {obj.moneda} {obj.precio} (desde {obj.vigencia_inicio})."
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_initial(self):
        initial = super().get_initial()
        rq = self.request
        # Prefiere querystring; si no hay, usa sucursal activa si tu Tenancy la expone
        if 'sucursal' in rq.GET:
            initial['sucursal'] = rq.GET.get('sucursal')
        elif getattr(rq, 'sucursal_activa', None):
            initial['sucursal'] = rq.sucursal_activa.id
        if 'servicio' in rq.GET:
            initial['servicio'] = rq.GET.get('servicio')
        if 'tipo' in rq.GET:
            initial['tipo_vehiculo'] = rq.GET.get('tipo')
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa
        user = self.request.user
        ctx["puede_crear"] = has_empresa_perm(
            user, empresa, Perm.PRICING_CREATE)
        # por claridad, en create no mostramos editar; pero lo dejamos en False explícito
        ctx["puede_editar"] = False
        return ctx


# ============================================================
# Edición
# ============================================================

class PriceUpdateView(EmpresaPermRequiredMixin, BackUrlMixin, UpdateView):
    """
    Edición de precio. Usa `update_price` para centralizar validaciones y
    permitir cambios de fechas/estado de forma segura.
    """
    model = PrecioServicio
    form_class = PriceForm
    template_name = "pricing/form.html"
    default_url_name = "pricing:list"
    required_perms = (Perm.PRICING_EDIT,)

    @property
    def empresa(self):
        return getattr(self, "empresa_activa", None) or getattr(self.request, "empresa_activa", None)

    def get_queryset(self):
        """
        Restringe edición a objetos de la empresa activa (multi-tenant).
        """
        empresa = self.empresa
        base = super().get_queryset()
        if not empresa:
            return base.none()
        return base.filter(empresa=empresa)

    def get_form_kwargs(self):
        """
        Inyecta `empresa` al formulario para limitar FKs al tenant activo.
        """
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form: PriceForm):
        obj: PrecioServicio = self.get_object()
        cd = form.cleaned_data

        obj = update_price(
            obj,
            precio=cd.get("precio"),
            moneda=cd.get("moneda"),
            vigencia_inicio=cd.get("vigencia_inicio"),
            vigencia_fin=cd.get("vigencia_fin"),
            activo=cd.get("activo"),
        )
        messages.success(
            self.request,
            f"Cambios guardados: {obj.servicio} × {obj.tipo_vehiculo} @ {obj.sucursal} - {obj.moneda} {obj.precio} ({obj.periodo_str})."
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa
        user = self.request.user
        ctx["puede_editar"] = has_empresa_perm(
            user, empresa, Perm.PRICING_EDIT)
        # opcional: si querés mostrar un botón "Duplicar como nuevo" que use crear
        ctx["puede_crear"] = has_empresa_perm(
            user, empresa, Perm.PRICING_CREATE)
        return ctx


class PriceDeactivateView(EmpresaPermRequiredMixin, View):
    """
    Soft-delete: marca inactivo y cierra vigencia (si está abierta).
    POST-only.
    """
    required_perms = (Perm.PRICING_DEACTIVATE,)

    @property
    def empresa(self):
        return getattr(self, "empresa_activa", None) or getattr(self.request, "empresa_activa", None)

    def post(self, request, pk: int):
        empresa = self.empresa
        obj = get_object_or_404(PrecioServicio, pk=pk, empresa=empresa)

        # Cerrar vigencia si está abierta
        if obj.vigencia_fin is None:
            obj.vigencia_fin = localdate()

        obj.activo = False
        obj.save(update_fields=["vigencia_fin", "activo"])

        messages.success(request, "Precio desactivado y vigencia cerrada.")
        next_url = request.POST.get("next") or reverse("pricing:list")
        return redirect(next_url)
