# apps/catalog/views.py
from __future__ import annotations
from typing import Any, Dict, Optional

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from apps.catalog.forms.service import ServiceForm
from apps.catalog import selectors
from apps.catalog.services import (
    crear_servicio,
    editar_servicio,
    activar_servicio,
    desactivar_servicio,
)
from apps.org.permissions import (
    EmpresaPermRequiredMixin,
    has_empresa_perm,
    Perm,
)
from apps.org.models import Empresa


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


# -------------------
# Listado
# -------------------

class ServiceListView(EmpresaPermRequiredMixin, ListView):
    """
    Listado de servicios con búsqueda `?q=` y paginación.
    """
    required_perms = (Perm.CATALOG_VIEW,)
    template_name = "catalog/list.html"
    context_object_name = "servicios"
    paginate_by = 20

    def get_queryset(self):
        q = (self.request.GET.get("q") or "").strip()
        return selectors.buscar_servicios(self.empresa_activa, q)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        # Flags de permisos
        ctx["puede_crear"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_CREATE)
        ctx["puede_editar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_EDIT)
        ctx["puede_activar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_ACTIVATE)
        ctx["puede_desactivar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_DEACTIVATE)
        ctx["puede_eliminar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_DELETE)
        return ctx


class ServiceDetailView(EmpresaPermRequiredMixin, DetailView):
    """
    Muestra detalle de un servicio de la empresa activa.
    """
    required_perms = (Perm.CATALOG_VIEW,)
    template_name = "catalog/detail.html"
    context_object_name = "object"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        obj = selectors.get_servicio_por_id(self.empresa_activa, pk)
        if obj is None:
            messages.error(
                self.request, "El servicio no existe o no pertenece a la empresa activa."
            )
            raise self.handle_no_permission()
        return obj

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["puede_editar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_EDIT)
        ctx["puede_activar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_ACTIVATE)
        ctx["puede_desactivar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_DEACTIVATE)
        ctx["puede_eliminar"] = has_empresa_perm(
            self.request.user, self.empresa_activa, Perm.CATALOG_DELETE)
        return ctx


# -------------------
# Alta
# -------------------

class ServiceCreateView(EmpresaPermRequiredMixin, NextUrlMixin, CreateView):
    """
    Alta de servicio.
    """
    required_perms = (Perm.CATALOG_CREATE,)
    template_name = "catalog/form.html"
    form_class = ServiceForm
    default_success_url = reverse_lazy("catalog:services")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: ServiceForm) -> HttpResponse:
        data = form.cleaned_data
        try:
            result = crear_servicio(
                empresa=self.empresa_activa,
                nombre=data.get("nombre"),
                descripcion=data.get("descripcion") or "",
                slug=data.get("slug") or None,
            )
        except Exception as e:
            form.add_error(None, e)
            return self.form_invalid(form)

        messages.success(
            self.request, f"Servicio “{result.servicio.nombre}” creado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


# -------------------
# Edición
# -------------------

class ServiceUpdateView(EmpresaPermRequiredMixin, NextUrlMixin, UpdateView):
    """
    Edición de servicio.
    """
    required_perms = (Perm.CATALOG_EDIT,)
    template_name = "catalog/form.html"
    form_class = ServiceForm
    default_success_url = reverse_lazy("catalog:services")

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        obj = selectors.get_servicio_por_id(self.empresa_activa, pk)
        if obj is None:
            messages.error(
                self.request, "El servicio no existe o no pertenece a la empresa activa.")
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
                empresa=self.empresa_activa,
                servicio_id=self.object.pk,
                nombre=data.get("nombre"),
                descripcion=data.get("descripcion"),
                slug=data.get("slug") or None,
                activo=data.get("activo"),
            )
        except Exception as e:
            form.add_error(None, e)
            return self.form_invalid(form)

        messages.success(
            self.request, f"Servicio “{result.servicio.nombre}” actualizado.")
        return HttpResponseRedirect(self.get_success_url())


# ---------------------------
# Activar / Desactivar
# ---------------------------

class ServiceDeactivateView(EmpresaPermRequiredMixin, View):
    """
    Marca un servicio como inactivo. Solo acepta POST.
    """
    required_perms = (Perm.CATALOG_DEACTIVATE,)

    def post(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        try:
            res = desactivar_servicio(
                empresa=self.empresa_activa, servicio_id=pk)
            messages.success(
                request, f"Servicio “{res.servicio.nombre}” desactivado.")
        except Exception as e:
            messages.error(request, f"No se pudo desactivar el servicio: {e}")
        next_url = request.POST.get("next") or reverse_lazy("catalog:services")
        return redirect(next_url)


class ServiceActivateView(EmpresaPermRequiredMixin, View):
    """
    Reactiva un servicio previamente inactivo. Solo acepta POST.
    """
    required_perms = (Perm.CATALOG_ACTIVATE,)

    def post(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        try:
            res = activar_servicio(empresa=self.empresa_activa, servicio_id=pk)
            messages.success(
                request, f"Servicio “{res.servicio.nombre}” activado.")
        except Exception as e:
            messages.error(request, f"No se pudo activar el servicio: {e}")
        next_url = request.POST.get("next") or reverse_lazy("catalog:services")
        return redirect(next_url)


# -------------------
# Eliminación
# -------------------

class ServiceDeleteView(EmpresaPermRequiredMixin, View):
    """
    Elimina un servicio de forma definitiva. Solo acepta POST.
    """
    required_perms = (Perm.CATALOG_DELETE,)

    def post(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        try:
            obj = selectors.get_servicio_por_id(self.empresa_activa, pk)
            if not obj:
                messages.error(
                    request, "El servicio no existe o no pertenece a la empresa activa.")
            else:
                obj.delete()
                messages.success(
                    request, f"Servicio “{obj.nombre}” eliminado definitivamente.")
        except Exception as e:
            messages.error(request, f"No se pudo eliminar el servicio: {e}")
        next_url = request.POST.get("next") or reverse_lazy("catalog:services")
        return redirect(next_url)
