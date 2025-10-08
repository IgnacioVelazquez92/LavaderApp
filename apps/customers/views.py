# apps/customers/views.py
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.functional import cached_property
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from django.db.models import Prefetch, Q, Count

from .models import Cliente
from apps.vehicles.models import Vehiculo
from .forms import CustomerForm
from apps.vehicles import selectors as vehicle_selectors

# ✅ permisos
from apps.org.permissions import Perm, has_empresa_perm, EmpresaPermRequiredMixin


# =============================================================================
# Mixins
# =============================================================================

class TenancyMixin:
    """
    Requiere que TenancyMiddleware haya seteado:
      - request.empresa_activa  (FK a org.Empresa o None)
    """

    @cached_property
    def empresa(self):
        empresa = getattr(self.request, "empresa_activa", None)
        if not empresa:
            raise PermissionDenied("No hay empresa activa en el contexto.")
        return empresa


# =============================================================================
# Vistas
# =============================================================================

class CustomerListView(EmpresaPermRequiredMixin, TenancyMixin, ListView):
    """
    Listado paginado de clientes del tenant (empresa) con búsqueda y filtros.

    Query params:
      - q: cadena de búsqueda (nombre, apellido, razón social, email, tel, doc)
      - estado: 'activos' (default) | 'inactivos' | 'todos'
    """
    template_name = "customers/list.html"
    model = Cliente
    context_object_name = "items"
    paginate_by = 20

    # 🔐 permiso requerido
    required_perms = [Perm.CUSTOMERS_VIEW]

    def get_queryset(self):
        qs = (
            Cliente.objects
            .filter(empresa=self.empresa)
            .select_related("empresa")
            .order_by("razon_social", "apellido", "nombre")
        )

        q = (self.request.GET.get("q") or "").strip()
        estado = (self.request.GET.get("estado") or "activos").lower()

        if estado == "activos":
            qs = qs.filter(activo=True)
        elif estado == "inactivos":
            qs = qs.filter(activo=False)
        # 'todos' no filtra por activo

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(apellido__icontains=q)
                | Q(razon_social__icontains=q)
                | Q(email__icontains=q)
                | Q(documento__icontains=q)
                | Q(tel_wpp__icontains=q)
                | Q(tel_busqueda__icontains=q)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["estado"] = self.request.GET.get("estado", "activos").lower()

        # Flags de UI por permiso (usando has_empresa_perm)
        ctx["puede_crear_cliente"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.CUSTOMERS_CREATE)
        return ctx


class CustomerCreateView(EmpresaPermRequiredMixin, TenancyMixin, CreateView):
    """
    Alta de cliente scoped por empresa.

    - Inyectamos request al form para que el form setee empresa/creado_por
      y aplique normalizaciones (tel E.164, lower(email), etc.).
    - Si hay errores en save() (ValidationError/IntegrityError mapeados al form),
      NO redirige: re-renderiza el form con errores (HTTP 200).
    """
    template_name = "customers/form.html"
    model = Cliente
    form_class = CustomerForm
    success_url = reverse_lazy("customers:list")

    # 🔐 permiso requerido
    required_perms = [Perm.CUSTOMERS_CREATE]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # para que el form acceda a empresa/user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        """
        Evitamos usar super().form_valid() para poder inspeccionar si el form
        acumuló errores durante save() (p.ej. por constraints) y, en ese caso,
        responder con form_invalid().
        """
        self.object = form.save(commit=True)
        if form.errors:
            return self.form_invalid(form)
        messages.success(self.request, "Cliente creado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


class CustomerUpdateView(EmpresaPermRequiredMixin, TenancyMixin, UpdateView):
    """
    Edición de cliente. Se asegura de que el objeto pertenezca a la empresa activa.
    Si save() mapea errores al form, NO redirige.
    """
    template_name = "customers/form.html"
    model = Cliente
    form_class = CustomerForm
    success_url = reverse_lazy("customers:list")

    # 🔐 permiso requerido
    required_perms = [Perm.CUSTOMERS_EDIT]

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            raise Http404("Cliente no encontrado en esta empresa.")
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=True)
        if form.errors:
            return self.form_invalid(form)
        messages.success(self.request, "Cliente actualizado.")
        return HttpResponseRedirect(self.get_success_url())


class CustomerDetailView(EmpresaPermRequiredMixin, TenancyMixin, DetailView):
    model = Cliente
    template_name = "customers/detail.html"
    context_object_name = "obj"

    # 🔐 permiso requerido
    required_perms = [Perm.CUSTOMERS_VIEW]

    def get_queryset(self):
        qs = super().get_queryset().filter(empresa=self.empresa)

        # Prefetch de vehículos activos (para mostrar en listado)
        vehiculos_activos_qs = (
            Vehiculo.objects
            .filter(empresa=self.empresa, activo=True)
            .only("id", "patente", "marca", "modelo", "tipo_id")
            .select_related("tipo")
        )
        qs = qs.prefetch_related(
            Prefetch("vehiculos", queryset=vehiculos_activos_qs,
                     to_attr="vehiculos_activos")
        ).annotate(
            vehiculos_activos_count=Count(
                "vehiculos", filter=Q(vehiculos__activo=True))
        )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["vehiculos"] = vehicle_selectors.vehiculos_de_cliente(
            empresa=self.empresa, cliente=self.object, solo_activos=False
        )
        # Flags de UI por permiso
        ctx["puede_editar"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.CUSTOMERS_EDIT)
        ctx["puede_desactivar"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.CUSTOMERS_DEACTIVATE)
        ctx["puede_eliminar"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.CUSTOMERS_DELETE)
        return ctx
