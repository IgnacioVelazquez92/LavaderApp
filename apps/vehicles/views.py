"""
views.py — CBVs del módulo Vehicles
- Vehículos: List, Create, Update, Detail, Activar, Desactivar
- Tipos de vehículo: List, Create, Update, Activar, Desactivar

Convenciones:
- Todas las vistas requieren autenticación.
- Se asume TenancyMiddleware inyectando request.empresa_activa.
- Se usan services para mutaciones y selectors para lecturas.
"""

from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.views.generic.detail import SingleObjectMixin

from apps.customers.models import Cliente
from . import selectors, services
from .forms import VehicleForm, VehicleFilterForm, TipoVehiculoForm
from .models import Vehiculo, TipoVehiculo


# ==============================
# Mixins utilitarios
# ==============================

class EmpresaContextMixin:
    """
    Garantiza que exista empresa activa en el request.
    Provee self.empresa y helpers de success_url para nombres comunes.
    """

    def dispatch(self, request, *args, **kwargs):
        self.empresa = getattr(request, "empresa_activa", None)
        if not self.empresa:
            # Podés redirigir a onboarding o mostrar un error claro
            messages.error(
                request, "Primero creá/activá un Lavadero para continuar.")
            return redirect(reverse("org:empresas"))
        return super().dispatch(request, *args, **kwargs)

    # Nombres por defecto que se usan en este módulo (ajustá si tu routing difiere)
    vehicles_list_url = "vehicles:list"
    types_list_url = "vehicles:types_list"

    def success_url(self, name: str = None):
        """
        Atajo para generar reverse_lazy de rutas locales.
        """
        if name is None:
            name = self.vehicles_list_url
        return reverse_lazy(name)


class EmpresaQuerysetMixin(EmpresaContextMixin):
    """
    Restringe get_queryset() por empresa para Vehiculo/TipoVehiculo.
    """

    model = None  # debe setearse en subclases

    def get_queryset(self):
        if self.model is Vehiculo:
            return Vehiculo.objects.select_related("cliente", "tipo").filter(empresa=self.empresa)
        if self.model is TipoVehiculo:
            return TipoVehiculo.objects.filter(empresa=self.empresa)
        raise NotImplementedError(
            "Definí 'model' en la subclase o overrideá get_queryset().")


class BackUrlMixin:
    back_fallback_name = None  # ej. "vehicles:list"

    def get_back_url(self):
        return (self.request.GET.get("next")
                or self.request.META.get("HTTP_REFERER")
                or (reverse_lazy(self.back_fallback_name) if self.back_fallback_name else "/"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["back_url"] = self.get_back_url()
        return ctx

# ==============================
# Vehículos
# ==============================


class VehicleListView(LoginRequiredMixin, EmpresaContextMixin, ListView):
    """
    Listado de vehículos con filtros (cliente, q, solo_activos) y KPIs por tipo.
    """
    template_name = "vehicles/list.html"
    context_object_name = "vehiculos"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = VehicleFilterForm(
            self.request.GET or None, empresa=self.empresa)
        if self.filter_form.is_valid():
            q = self.filter_form.cleaned_data.get("q")
            cliente = self.filter_form.cleaned_data.get("cliente")
            solo_activos = self.filter_form.cleaned_data.get("solo_activos")
        else:
            q, cliente, solo_activos = "", None, True

        return selectors.buscar_vehiculos(
            empresa=self.empresa,
            q=q,
            cliente=cliente,
            solo_activos=solo_activos,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.filter_form
        ctx["stats_por_tipo"] = selectors.stats_por_tipo(empresa=self.empresa)
        return ctx


class VehicleCreateView(LoginRequiredMixin, EmpresaContextMixin, CreateView):
    """
    Alta de vehículo utilizando VehicleForm y service.crear_vehiculo.
    """
    form_class = VehicleForm
    template_name = "vehicles/form.html"
    success_url = reverse_lazy("vehicles:list")
    back_fallback_name = "vehicles:list"

    def get_initial(self):
        initial = super().get_initial()
        cid = self.request.GET.get("cliente")
        if cid:
            initial["cliente"] = cid
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        obj = services.crear_vehiculo(
            empresa=self.empresa,
            user=self.request.user,
            cliente=data["cliente"],
            tipo=data.get("tipo"),
            marca=data.get("marca", ""),
            modelo=data.get("modelo", ""),
            anio=data.get("anio"),
            color=data.get("color", ""),
            patente=data["patente"],
            notas=data.get("notas", ""),
            activo=data.get("activo", True),
        )
        self.object = obj
        messages.success(self.request, "Vehículo creado con éxito.")
        # Redirección: si viene ?next, respetarla; si se envió ?cliente=... podrías ir al detalle del cliente.
        next_url = self.request.POST.get(
            "next") or self.request.GET.get("next")
        return redirect(next_url or self.get_success_url())

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            back = self.request.GET.get(
                "next") or self.request.META.get("HTTP_REFERER")
            ctx["back_url"] = back or str(self.success_url)  # fallback seguro
            return ctx


class VehicleUpdateView(LoginRequiredMixin, EmpresaQuerysetMixin, UpdateView):
    """
    Edición de vehículo. Valida tenant y unicidad de patente si cambia.
    """
    model = Vehiculo
    form_class = VehicleForm
    template_name = "vehicles/form.html"
    success_url = reverse_lazy("vehicles:list")
    back_fallback_name = "vehicles:list"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "No podés editar vehículos de otra empresa.")
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        self.object = services.editar_vehiculo(
            empresa=self.empresa,
            user=self.request.user,
            vehiculo=self.object,
            cliente=data.get("cliente"),
            tipo=data.get("tipo"),
            marca=data.get("marca"),
            modelo=data.get("modelo"),
            anio=data.get("anio"),
            color=data.get("color"),
            patente=data.get("patente"),
            notas=data.get("notas"),
            activo=data.get("activo"),
        )
        messages.success(self.request, "Vehículo actualizado.")
        next_url = self.request.GET.get("next")
        return redirect(next_url or self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        back = self.request.GET.get(
            "next") or self.request.META.get("HTTP_REFERER")
        ctx["back_url"] = back or str(self.success_url)  # fallback seguro
        return ctx


class VehicleDetailView(LoginRequiredMixin, EmpresaQuerysetMixin, DetailView):
    """
    Detalle de vehículo. Útil para ver historial y próximas integraciones.
    """
    model = Vehiculo
    template_name = "vehicles/detail.html"
    context_object_name = "vehiculo"
    back_fallback_name = "vehicles:list"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            raise PermissionDenied("No podés ver vehículos de otra empresa.")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Acá podrías sumar historial de lavados/ventas cuando el módulo esté disponible
        return ctx


class VehicleActivateView(LoginRequiredMixin, EmpresaQuerysetMixin, SingleObjectMixin, View):
    """
    POST: Activa (soft-undelete) un vehículo.
    """
    model = Vehiculo
    success_url = reverse_lazy("vehicles:list")

    def post(self, request, *args, **kwargs):
        vehiculo = self.get_object()
        if vehiculo.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "No podés activar vehículos de otra empresa.")
        services.activar_vehiculo(
            empresa=self.empresa, user=request.user, vehiculo=vehiculo)
        messages.success(request, f"Vehículo {vehiculo.patente} activado.")
        return redirect(request.POST.get("next") or self.success_url)


class VehicleDeactivateView(LoginRequiredMixin, EmpresaQuerysetMixin, SingleObjectMixin, View):
    """
    POST: Desactiva (soft delete) un vehículo.
    """
    model = Vehiculo
    success_url = reverse_lazy("vehicles:list")

    def post(self, request, *args, **kwargs):
        vehiculo = self.get_object()
        if vehiculo.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "No podés desactivar vehículos de otra empresa.")
        services.desactivar_vehiculo(
            empresa=self.empresa, user=request.user, vehiculo=vehiculo)
        messages.success(request, f"Vehículo {vehiculo.patente} desactivado.")
        return redirect(request.POST.get("next") or self.success_url)


# ==============================
# Tipos de vehículo
# ==============================

# apps/vehicles/views.py

class TipoVehiculoListView(LoginRequiredMixin, EmpresaQuerysetMixin, ListView):
    model = TipoVehiculo
    template_name = "vehicles/types_list.html"
    context_object_name = "tipos"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()

        # Parseo de filtros en la VISTA (default: solo_activos=True)
        raw = self.request.GET.get("solo_activos", "1")
        self.solo_activos = str(raw).lower() in ("1", "true", "on", "yes")
        self.q = (self.request.GET.get("q") or "").strip()

        if self.solo_activos:
            qs = qs.filter(activo=True)
        if self.q:
            qs = qs.filter(nombre__icontains=self.q)

        return qs.order_by("nombre")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Para el template:
        ctx["solo_activos"] = self.solo_activos
        ctx["q"] = self.q

        # (Opcional) back_url coherente
        back = self.request.GET.get(
            "next") or self.request.META.get("HTTP_REFERER")
        ctx["back_url"] = back or str(self.success_url) if hasattr(
            self, "success_url") else ""
        return ctx


class TipoVehiculoCreateView(LoginRequiredMixin, EmpresaContextMixin, CreateView):
    """
    Alta de tipo de vehículo con validación (empresa, slug único).
    """
    form_class = TipoVehiculoForm
    template_name = "vehicles/type_form.html"
    success_url = reverse_lazy("vehicles:types_list")
    back_fallback_name = "vehicles:types_list"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        obj = services.crear_tipo_vehiculo(
            empresa=self.empresa,
            user=self.request.user,
            nombre=data["nombre"],
            slug=data["slug"],
            activo=data["activo"],
        )
        self.object = obj
        messages.success(self.request, "Tipo de vehículo creado.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        back = self.request.GET.get(
            "next") or self.request.META.get("HTTP_REFERER")
        ctx["back_url"] = back or str(self.success_url)  # fallback seguro
        return ctx


class TipoVehiculoUpdateView(LoginRequiredMixin, EmpresaQuerysetMixin, UpdateView):
    """
    Edición de tipo de vehículo (valida tenant y unicidad de slug).
    """
    model = TipoVehiculo
    form_class = TipoVehiculoForm
    template_name = "vehicles/type_form.html"
    success_url = reverse_lazy("vehicles:types_list")
    back_fallback_name = "vehicles:types_list"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            raise PermissionDenied("No podés editar tipos de otra empresa.")
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        self.object = services.editar_tipo_vehiculo(
            empresa=self.empresa,
            user=self.request.user,
            tipo=self.object,
            nombre=data["nombre"],
            slug=data["slug"],
            activo=data["activo"],
        )
        messages.success(self.request, "Tipo de vehículo actualizado.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        back = self.request.GET.get(
            "next") or self.request.META.get("HTTP_REFERER")
        ctx["back_url"] = back or str(self.success_url)  # fallback seguro
        return ctx


class TipoVehiculoActivateView(LoginRequiredMixin, EmpresaQuerysetMixin, SingleObjectMixin, View):
    """
    POST: Activa un tipo de vehículo.
    """
    model = TipoVehiculo
    success_url = reverse_lazy("vehicles:types_list")

    def post(self, request, *args, **kwargs):
        tipo = self.get_object()
        if tipo.empresa_id != self.empresa.id:
            raise PermissionDenied("No podés activar tipos de otra empresa.")
        services.activar_tipo_vehiculo(
            empresa=self.empresa, user=request.user, tipo=tipo)
        messages.success(request, f"Tipo '{tipo.nombre}' activado.")
        return redirect(request.POST.get("next") or self.success_url)


class TipoVehiculoDeactivateView(LoginRequiredMixin, EmpresaQuerysetMixin, SingleObjectMixin, View):
    """
    POST: Desactiva un tipo de vehículo.
    """
    model = TipoVehiculo
    success_url = reverse_lazy("vehicles:types_list")

    def post(self, request, *args, **kwargs):
        tipo = self.get_object()
        if tipo.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "No podés desactivar tipos de otra empresa.")
        services.desactivar_tipo_vehiculo(
            empresa=self.empresa, user=request.user, tipo=tipo)
        messages.success(request, f"Tipo '{tipo.nombre}' desactivado.")
        return redirect(request.POST.get("next") or self.success_url)
