# apps/catalog/views.py
from __future__ import annotations
from django.views.generic import DetailView

from typing import Any, Dict, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from apps.catalog.forms.service import ServiceForm
from apps.catalog import selectors
from apps.catalog.services import (
    crear_servicio,
    editar_servicio,
    activar_servicio,
    desactivar_servicio,
)
from apps.org.models import Empresa


# --------------------
# Mixins utilitarios
# --------------------

class EmpresaContextMixin:
    """
    Garantiza que exista empresa activa en el request.
    Provee `self.empresa`.
    """
    empresa: Empresa

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        empresa = getattr(request, "empresa_activa", None)
        if empresa is None:
            messages.error(request, "No hay una empresa activa seleccionada.")
            return redirect("org:empresas")  # o al panel "/"
        self.empresa = empresa
        return super().dispatch(request, *args, **kwargs)


class NextUrlMixin:
    """
    Soporte para `?next=` en GET/POST con prioridad sobre success_url.
    """
    default_success_url: str = ""

    def get_next_url(self) -> Optional[str]:
        req = self.request
        return (
            req.POST.get("next")
            or req.GET.get("next")
            or None
        )

    def get_success_url(self) -> str:
        return self.get_next_url() or self.default_success_url


# -------------
# Listado
# -------------

class ServiceListView(LoginRequiredMixin, EmpresaContextMixin, ListView):
    """
    Listado de servicios con búsqueda `?q=` y paginación.
    """
    template_name = "catalog/list.html"
    context_object_name = "servicios"
    paginate_by = 20

    def get_queryset(self):
        q = (self.request.GET.get("q") or "").strip()
        return selectors.buscar_servicios(self.empresa, q)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        return ctx


class ServiceDetailView(LoginRequiredMixin, EmpresaContextMixin, DetailView):
    """
    Muestra detalle de un servicio de la empresa activa.
    """
    template_name = "catalog/detail.html"
    context_object_name = "object"  # default, pero lo dejamos explícito

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        obj = selectors.get_servicio_por_id(self.empresa, pk)
        if obj is None:
            messages.error(
                self.request, "El servicio no existe o no pertenece a la empresa activa.")
            raise self.handle_no_permission()
        return obj

# -------------
# Alta
# -------------


class ServiceCreateView(LoginRequiredMixin, EmpresaContextMixin, NextUrlMixin, CreateView):
    """
    Alta de servicio.
    - Forzamos activo=True en el form (ya contemplado en ServiceForm).
    """
    template_name = "catalog/form.html"
    form_class = ServiceForm
    default_success_url = reverse_lazy("catalog:services")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pasamos request para que el form conozca empresa_activa
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: ServiceForm) -> HttpResponse:
        # Usamos el service para centralizar validaciones y efectos
        data = form.cleaned_data
        try:
            result = crear_servicio(
                empresa=self.empresa,
                nombre=data.get("nombre"),
                descripcion=data.get("descripcion") or "",
                slug=data.get("slug") or None,
                # creado_por=self.request.user.id  # si luego se usa auditoría
            )
        except Exception as e:
            form.add_error(None, e)
            return self.form_invalid(form)

        messages.success(
            self.request, f"Servicio “{result.servicio.nombre}” creado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


# -------------
# Edición
# -------------

class ServiceUpdateView(LoginRequiredMixin, EmpresaContextMixin, NextUrlMixin, UpdateView):
    """
    Edición de servicio.
    """
    template_name = "catalog/form.html"
    form_class = ServiceForm
    default_success_url = reverse_lazy("catalog:services")

    # Obtenemos el objeto respetando el scope de empresa
    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        obj = selectors.get_servicio_por_id(self.empresa, pk)
        if obj is None:
            messages.error(
                self.request, "El servicio no existe o no pertenece a la empresa activa.")
            # provoca redirect a login por LoginRequired; si querés, redirige a listado
            raise self.handle_no_permission()
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: ServiceForm) -> HttpResponse:
        data = form.cleaned_data
        try:
            result = editar_servicio(
                empresa=self.empresa,
                servicio_id=self.object.pk,
                nombre=data.get("nombre"),
                descripcion=data.get("descripcion"),
                slug=data.get("slug") or None,
                activo=data.get("activo"),
                # editado_por=self.request.user.id,
            )
        except Exception as e:
            form.add_error(None, e)
            return self.form_invalid(form)

        messages.success(
            self.request, f"Servicio “{result.servicio.nombre}” actualizado.")
        return HttpResponseRedirect(self.get_success_url())


# ---------------------------
# Activar / Desactivar (POST)
# ---------------------------

class ServiceDeactivateView(LoginRequiredMixin, EmpresaContextMixin, View):
    """
    Marca un servicio como inactivo. Solo acepta POST.
    """

    def post(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        try:
            res = desactivar_servicio(empresa=self.empresa, servicio_id=pk)
            messages.success(
                request, f"Servicio “{res.servicio.nombre}” desactivado.")
        except Exception as e:
            messages.error(request, f"No se pudo desactivar el servicio: {e}")
        next_url = request.POST.get("next") or reverse_lazy("catalog:services")
        return redirect(next_url)


class ServiceActivateView(LoginRequiredMixin, EmpresaContextMixin, View):
    """
    Reactiva un servicio previamente inactivo. Solo acepta POST.
    """

    def post(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        try:
            res = activar_servicio(empresa=self.empresa, servicio_id=pk)
            messages.success(
                request, f"Servicio “{res.servicio.nombre}” activado.")
        except Exception as e:
            messages.error(request, f"No se pudo activar el servicio: {e}")
        next_url = request.POST.get("next") or reverse_lazy("catalog:services")
        return redirect(next_url)
