# apps/pricing/views.py
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Iterable, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, CreateView, UpdateView

from .forms.price import PriceForm
from .models import PrecioServicio
from .selectors import listar_precios
from .services.pricing import PrecioCmd, create_or_replace, update_price


# ============================================================
# Utilidades de vistas
# ============================================================

class EmpresaRoleRequiredMixin(UserPassesTestMixin):
    """
    Chequeo de rol por empresa activa (muy liviano para MVP).
    Permite: superuser SIEMPRE. Si no, verifica membresía en la empresa activa
    con rol dentro de `allowed_roles`.

    - Se asume un modelo accounts.EmpresaMembership con campos:
        user (FK a User), empresa (FK a org.Empresa), rol (str)
      y roles esperados: 'admin', 'operador', 'auditor' (al menos).
    - Si tu proyecto centraliza permisos en otro lugar (p.ej. lavaderos.permissions),
      podés reemplazar test_func para delegar ahí.
    """

    allowed_roles: Iterable[str] = ()

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        empresa = getattr(self.request, "empresa_activa", None)
        if not empresa:
            return False

        # Import local para evitar dependencias circulares al cargar apps
        from apps.accounts.models import EmpresaMembership  # type: ignore

        return EmpresaMembership.objects.filter(
            user=user, empresa=empresa, rol__in=self.allowed_roles
        ).exists()


class BackUrlMixin:
    """
    Provee soporte de retorno consistente:
    - Prioriza querystring `?next=...`
    - Fallback configurable vía `default_url`
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

class PriceListView(LoginRequiredMixin, EmpresaRoleRequiredMixin, ListView):
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
    allowed_roles = ("admin", "operador")
    default_url_name = "pricing:list"

    def get_queryset(self):
        empresa = getattr(self.request, "empresa_activa", None)
        if not empresa:
            # Sin empresa activa, queryset vacío.
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
        empresa = getattr(self.request, "empresa_activa", None)
        if empresa:
            from apps.org.models import Sucursal
            from apps.catalog.models import Servicio
            from apps.vehicles.models import TipoVehiculo
            ctx["sucursales"] = Sucursal.objects.filter(
                empresa=empresa,).order_by("nombre")
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
        return ctx


# ============================================================
# Alta
# ============================================================

class PriceCreateView(LoginRequiredMixin, EmpresaRoleRequiredMixin, BackUrlMixin, CreateView):
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
    allowed_roles = ("admin",)
    default_url_name = "pricing:list"

    def get_form_kwargs(self):
        """
        Inyecta `empresa` al formulario para limitar querysets y asignar empresa en save().
        """
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = getattr(self.request, "empresa_activa", None)
        return kwargs

    def form_valid(self, form: PriceForm):
        empresa = getattr(self.request, "empresa_activa", None)
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
        # Prefiere querystring; si no hay, usa sucursal activa
        if 'sucursal' in rq.GET:
            initial['sucursal'] = rq.GET.get('sucursal')
        elif getattr(rq, 'sucursal_activa', None):
            initial['sucursal'] = rq.sucursal_activa.id
        if 'servicio' in rq.GET:
            initial['servicio'] = rq.GET.get('servicio')
        if 'tipo' in rq.GET:
            initial['tipo_vehiculo'] = rq.GET.get('tipo')
        return initial

# ============================================================
# Edición
# ============================================================


class PriceUpdateView(LoginRequiredMixin, EmpresaRoleRequiredMixin, BackUrlMixin, UpdateView):
    """
    Edición de precio. Usa `update_price` para centralizar validaciones y
    permitir cambios de fechas/estado de forma segura.
    """
    model = PrecioServicio
    form_class = PriceForm
    template_name = "pricing/form.html"
    allowed_roles = ("admin",)
    default_url_name = "pricing:list"

    def get_queryset(self):
        """
        Restringe edición a objetos de la empresa activa (multi-tenant).
        """
        empresa = getattr(self.request, "empresa_activa", None)
        base = super().get_queryset()
        if not empresa:
            return base.none()
        return base.filter(empresa=empresa)

    def get_form_kwargs(self):
        """
        Inyecta `empresa` al formulario para limitar FKs al tenant activo.
        """
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = getattr(self.request, "empresa_activa", None)
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
