from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.functional import cached_property
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from .models import Cliente
from .forms import CustomerForm


# =============================================================================
# Mixins
# =============================================================================

class TenancyMixin:
    """
    Requiere que TenancyMiddleware haya seteado:
      - request.empresa_activa  (FK a org.Empresa o None)
      - request.sucursal_activa (opcional; no se usa aquí)

    Provee helper para recuperar la empresa del contexto.
    """

    @cached_property
    def empresa(self):
        empresa = getattr(self.request, "empresa_activa", None)
        if not empresa:
            # Si no hay empresa en contexto, el flujo del sistema no debe continuar.
            # Podés redirigir al selector de empresa si lo preferís.
            raise PermissionDenied("No hay empresa activa en el contexto.")
        return empresa


class RoleRequiredMixin(UserPassesTestMixin):
    """
    Chequeo básico de rol contra la Empresa activa.
    Pensado para integrarse con tu modelo EmpresaMembership (apps.accounts).

    Por defecto permite: admin y operador (lectura/escritura),
    y deniega a roles no reconocidos. El auditor queda habilitado para lectura
    si la vista no redefine 'allowed_roles'.

    Si tu proyecto ya tiene helpers en apps.accounts.permissions, podés
    reemplazar 'test_func' por una consulta directa.
    """
    allowed_roles = (
        "admin", "operador")  # por defecto para vistas de escritura

    def get_user_role(self):
        """
        Recupera el rol del usuario en la empresa activa.
        Debe concordar con tu implementación de memberships.
        """
        # Ejemplo sin acoplar: si tenés un related_name "memberships" en Empresa:
        memb = self.empresa.memberships.filter(user=self.request.user).first()
        return getattr(memb, "rol", None)

    def test_func(self):
        rol = self.get_user_role()
        return bool(rol and (rol in self.allowed_roles))

    def handle_no_permission(self):
        # Si está autenticado pero sin permisos → 403
        if self.request.user.is_authenticated:
            raise PermissionDenied("No tenés permisos para esta acción.")
        # Si no está autenticado → delega a LoginRequiredMixin
        return super().handle_no_permission()


# =============================================================================
# Vistas
# =============================================================================

class CustomerListView(LoginRequiredMixin, TenancyMixin, ListView):
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
            # Búsqueda sobre varios campos (incluye tel_busqueda para matches laxos)
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
        return ctx


class CustomerCreateView(LoginRequiredMixin, TenancyMixin, RoleRequiredMixin, CreateView):
    """
    Alta de cliente scoped por empresa.

    - En 'get_form_kwargs' inyectamos request para que el form setee empresa/creado_por
      y aplique normalizaciones (tel E.164, lower(email), etc.).
    - Redirige al listado con mensaje de éxito.
    """
    template_name = "customers/form.html"
    model = Cliente
    form_class = CustomerForm
    success_url = reverse_lazy("customers:list")
    allowed_roles = ("admin", "operador")  # escritura

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # para que el form acceda a empresa_activa/user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        resp = super().form_valid(form)
        messages.success(self.request, "Cliente creado correctamente.")
        return resp


class CustomerUpdateView(LoginRequiredMixin, TenancyMixin, RoleRequiredMixin, UpdateView):
    """
    Edición de cliente. Se asegura de que el objeto pertenezca a la empresa activa.
    """
    template_name = "customers/form.html"
    model = Cliente
    form_class = CustomerForm
    success_url = reverse_lazy("customers:list")
    allowed_roles = ("admin", "operador")  # escritura

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            # Evitamos acceder a registros de otra empresa
            raise Http404("Cliente no encontrado en esta empresa.")
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        resp = super().form_valid(form)
        messages.success(self.request, "Cliente actualizado.")
        return resp


class CustomerDetailView(LoginRequiredMixin, TenancyMixin, DetailView):
    """
    Detalle de cliente (solo lectura). Permite a 'auditor' visualizar.
    """
    template_name = "customers/detail.html"
    model = Cliente
    context_object_name = "obj"

    # Dejamos el control de acceso en el template/URL (solo login requerido).
    # Si quisieras restringir por rol, podés heredar de RoleRequiredMixin con allowed_roles
    # = ("admin", "operador", "auditor") y validar la membresía.

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa_id != self.empresa.id:
            raise Http404("Cliente no encontrado en esta empresa.")
        return obj
