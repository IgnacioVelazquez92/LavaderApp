# apps/org/views.py

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from apps.accounts.models import EmpresaMembership
from apps.org.forms.org import EmpresaForm, SucursalForm, EmpleadoForm
from apps.org.models import Empresa, Sucursal
from apps.org.permissions import EmpresaPermRequiredMixin, Perm
from apps.org.selectors import empresas_para_usuario


User = get_user_model()


# -------------------------------
# Helpers
# -------------------------------

def _set_empresa_activa_automatica(request):
    """ Pone en sesión la única empresa del usuario (si existe). """
    if not request.user.is_authenticated:
        return
    if request.session.get("empresa_id"):
        return
    emp = (
        Empresa.objects
        .filter(memberships__user=request.user, activo=True)
        .order_by("id")
        .first()
    )
    if emp:
        request.session["empresa_id"] = emp.pk


def _first_empresa_for(user):
    """ Devuelve la primera empresa del usuario (o None). """
    return (
        Empresa.objects
        .filter(memberships__user=user, activo=True)
        .order_by("id")
        .first()
    )


def _logout_user_everywhere(user):
    """ Invalida todas las sesiones de un usuario (logout global). """
    for s in Session.objects.all():
        data = s.get_decoded()
        if data.get("_auth_user_id") == str(user.pk):
            s.delete()


# -------------------------------
# Empresas
# -------------------------------

class EmpresaListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (Perm.ORG_VIEW,)
    model = Empresa
    template_name = "org/empresas.html"
    context_object_name = "empresas"

    def get_queryset(self):
        return Empresa.objects.filter(memberships__user=self.request.user).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["puede_crear_empresa"] = False
        return ctx


class EmpresaCreateView(CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = "org/empresa_form.html"

    def dispatch(self, request, *args, **kwargs):
        from django.conf import settings
        max_emp = getattr(settings, "SAAS_MAX_EMPRESAS_POR_USUARIO", 1)
        actuales = EmpresaMembership.objects.filter(user=request.user).count()
        if actuales >= max_emp:
            messages.info(
                request, "Ya tenés tu lavadero creado. Podés gestionar sus sucursales."
            )
            return redirect(reverse("org:sucursales"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = form.save()
        mem, _ = EmpresaMembership.objects.get_or_create(
            user=self.request.user,
            empresa=self.object,
            defaults={
                "rol": EmpresaMembership.ROLE_ADMIN,
                "activo": True,
                "is_owner": True,
            },
        )
        # Forzar flags correctos
        update_fields = []
        if mem.rol != EmpresaMembership.ROLE_ADMIN:
            mem.rol = EmpresaMembership.ROLE_ADMIN
            update_fields.append("rol")
        if not mem.activo:
            mem.activo = True
            update_fields.append("activo")
        if not mem.is_owner:
            mem.is_owner = True
            update_fields.append("is_owner")
        if update_fields:
            mem.save(update_fields=update_fields)

        self.request.session["empresa_id"] = self.object.pk
        self.request.session.pop("sucursal_id", None)

        messages.success(
            self.request, f"¡Lavadero creado! {self.object.nombre}")
        return redirect(reverse("org:sucursal_nueva"))

    def form_invalid(self, form):
        messages.error(
            self.request, "Revisá los campos marcados y volvé a intentar."
        )
        return super().form_invalid(form)


class EmpresaUpdateView(EmpresaPermRequiredMixin, UpdateView):
    required_perms = (Perm.ORG_EMPRESAS_MANAGE,)
    model = Empresa
    form_class = EmpresaForm
    template_name = "org/empresa_form.html"
    success_url = reverse_lazy("org:empresas")

    def form_valid(self, form):
        messages.success(self.request, "Cambios guardados.")
        return super().form_valid(form)


# -------------------------------
# Sucursales
# -------------------------------

class SucursalListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (Perm.ORG_VIEW,)
    model = Sucursal
    template_name = "org/sucursales.html"
    context_object_name = "sucursales"

    def get_queryset(self):
        _set_empresa_activa_automatica(self.request)
        empresa_id = self.request.session.get("empresa_id")
        return Sucursal.objects.filter(empresa_id=empresa_id)


class SucursalCreateView(EmpresaPermRequiredMixin, CreateView):
    required_perms = (Perm.ORG_SUCURSALES_MANAGE,)
    model = Sucursal
    form_class = SucursalForm
    template_name = "org/sucursal_form.html"
    success_url = reverse_lazy("org:sucursales")

    def _ensure_empresa_activa(self, request):
        _set_empresa_activa_automatica(request)
        return request.session.get("empresa_id")

    def form_valid(self, form):
        empresa_id = self._ensure_empresa_activa(self.request)
        if not empresa_id:
            messages.error(
                self.request, "Primero creá tu lavadero antes de agregar sucursales."
            )
            return redirect(reverse("org:empresa_nueva"))

        form.instance.empresa_id = empresa_id
        response = super().form_valid(form)

        cant = Sucursal.objects.filter(empresa_id=empresa_id).count()
        if cant == 1:
            messages.success(
                self.request, "Sucursal creada. ¡Listo para operar!")
            return redirect(reverse("home"))

        messages.success(self.request, "Sucursal creada con éxito.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(
            self.request, "Revisá los campos marcados y volvé a intentar."
        )
        return super().form_invalid(form)


class SucursalUpdateView(EmpresaPermRequiredMixin, UpdateView):
    required_perms = (Perm.ORG_SUCURSALES_MANAGE,)
    model = Sucursal
    form_class = SucursalForm
    template_name = "org/sucursal_form.html"
    success_url = reverse_lazy("org:sucursales")


# -------------------------------
# Selector / Post-login
# -------------------------------

class SelectorEmpresaView(View):
    """ Vista segura para seleccionar empresa/sucursal. """
    template_name = "org/selector.html"

    def get(self, request):
        empresa_id = request.session.get("empresa_id")
        if empresa_id:
            emp_valid = Empresa.objects.filter(
                pk=empresa_id, activo=True).exists()
            mem_valid = EmpresaMembership.objects.filter(
                user=request.user, empresa_id=empresa_id, activo=True
            ).exists()
            if not emp_valid or not mem_valid:
                request.session.pop("empresa_id", None)
                request.session.pop("sucursal_id", None)

        empresas = empresas_para_usuario(request.user)

        empresa_q = request.GET.get("empresa")
        if empresa_q:
            return self._activar_y_redirigir(request, empresa_q)

        if not request.session.get("empresa_id"):
            default_emp = (
                Empresa.objects
                .filter(
                    memberships__user=request.user,
                    memberships__activo=True,
                    activo=True,
                )
                .order_by("id")
                .first()
            )
            if default_emp:
                request.session["empresa_id"] = default_emp.pk

        from django.conf import settings
        max_emp = getattr(settings, "SAAS_MAX_EMPRESAS_POR_USUARIO", 1)
        actuales = EmpresaMembership.objects.filter(user=request.user).count()
        puede_crear_empresa = actuales < max_emp

        return render(
            request,
            self.template_name,
            {"empresas": empresas, "puede_crear_empresa": puede_crear_empresa},
        )

    def post(self, request):
        sucursal_id = request.POST.get("sucursal")
        if sucursal_id:
            empresa_id = request.session.get("empresa_id")
            if not empresa_id:
                emp = (
                    Empresa.objects
                    .filter(
                        memberships__user=request.user,
                        memberships__activo=True,
                        activo=True,
                    )
                    .order_by("id")
                    .first()
                )
                if not emp:
                    messages.error(request, "Primero creá tu lavadero.")
                    return redirect(reverse("org:empresa_nueva"))
                request.session["empresa_id"] = emp.pk
                empresa_id = emp.pk

            suc = get_object_or_404(
                Sucursal, pk=sucursal_id, empresa_id=empresa_id)
            request.session["sucursal_id"] = suc.pk
            messages.success(request, f"Sucursal activa: {suc.nombre}")
            next_url = request.GET.get("next") or request.POST.get(
                "next") or reverse("home")
            return redirect(next_url)

        empresa_id = request.POST.get("empresa")
        if not empresa_id:
            emp = (
                Empresa.objects
                .filter(
                    memberships__user=request.user,
                    memberships__activo=True,
                    activo=True,
                )
                .order_by("id")
                .first()
            )
            if not emp:
                messages.error(request, "Primero creá tu lavadero.")
                return redirect(reverse("org:empresa_nueva"))
            return self._activar_y_redirigir(request, emp.pk)

        return self._activar_y_redirigir(request, empresa_id)

    def _activar_y_redirigir(self, request, empresa_id):
        empresa = get_object_or_404(Empresa, pk=empresa_id, activo=True)
        es_miembro = EmpresaMembership.objects.filter(
            user=request.user, empresa=empresa, activo=True
        ).exists()
        if not es_miembro:
            messages.error(request, "No tenés acceso a esta empresa.")
            return redirect(reverse("home"))

        request.session["empresa_id"] = empresa.pk
        sucursal_id = request.session.get("sucursal_id")
        if sucursal_id and not Sucursal.objects.filter(pk=sucursal_id, empresa=empresa).exists():
            request.session.pop("sucursal_id", None)

        messages.success(request, f"Empresa activa: {empresa.nombre}")
        next_url = request.GET.get("next") or request.POST.get(
            "next") or reverse("home")
        return redirect(next_url)


class PostLoginRedirectView(View):
    def get(self, request, *args, **kwargs):
        mem_activa = (
            EmpresaMembership.objects
            .filter(user=request.user, activo=True)
            .select_related("empresa", "sucursal_asignada")
            .order_by("empresa_id")
            .first()
        )

        if not mem_activa:
            return redirect(reverse("org:empresa_nueva"))

        if not mem_activa.activo:
            messages.error(
                request, "Tu acceso está deshabilitado. Contactá al administrador."
            )
            return redirect(reverse("home"))

        request.session["empresa_id"] = mem_activa.empresa_id
        if mem_activa.sucursal_asignada_id:
            request.session["sucursal_id"] = mem_activa.sucursal_asignada_id

        if (
            mem_activa.rol == EmpresaMembership.ROLE_ADMIN
            and not Sucursal.objects.filter(empresa_id=mem_activa.empresa_id).exists()
        ):
            return redirect(reverse("org:sucursal_nueva"))

        return redirect(reverse("home"))


# -------------------------------
# Empleados
# -------------------------------

class EmpleadoListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    model = EmpresaMembership
    template_name = "org/empleados.html"
    context_object_name = "empleados"

    def get_queryset(self):
        return (
            EmpresaMembership.objects
            .filter(empresa=self.empresa_activa)
            .select_related("user", "sucursal_asignada", "empresa")
            .order_by("-is_owner", "user__email")
        )


class EmpleadoCreateView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    template_name = "org/empleado_form.html"

    def get(self, request):
        form = EmpleadoForm(empresa=self.empresa_activa)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = EmpleadoForm(request.POST, empresa=self.empresa_activa)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            rol = form.cleaned_data["rol"]
            sucursal = form.cleaned_data["sucursal_asignada"]
            password = form.cleaned_data["password_inicial"]

            user, _ = User.objects.get_or_create(
                email=email,
                defaults={"username": email,
                          "password": make_password(password)},
            )

            mem, _ = EmpresaMembership.objects.update_or_create(
                user=user,
                empresa=self.empresa_activa,
                defaults={"rol": rol,
                          "sucursal_asignada": sucursal, "activo": True},
            )

            if mem.is_owner is None:
                mem.is_owner = False
                mem.save(update_fields=["is_owner"])

            messages.success(
                request, f"Empleado {email} creado/actualizado correctamente."
            )
            return redirect("org:empleados")

        return render(request, self.template_name, {"form": form})


class EmpleadoUpdateView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    template_name = "org/empleado_form.html"

    def get_object(self, pk):
        return get_object_or_404(
            EmpresaMembership, pk=pk, empresa=self.empresa_activa
        )

    def get(self, request, pk):
        mem = self.get_object(pk)
        form = EmpleadoForm(
            initial={
                "email": mem.user.email,
                "rol": mem.rol,
                "sucursal_asignada": mem.sucursal_asignada,
            },
            empresa=self.empresa_activa,
        )
        return render(
            request,
            self.template_name,
            {"form": form, "editar": True, "membresia": mem},
        )

    def post(self, request, pk):
        mem = self.get_object(pk)
        if mem.is_owner:
            raise PermissionDenied("No se puede editar al propietario.")

        form = EmpleadoForm(request.POST, empresa=self.empresa_activa)
        if form.is_valid():
            mem.rol = form.cleaned_data["rol"]
            mem.sucursal_asignada = form.cleaned_data["sucursal_asignada"]
            mem.save(update_fields=["rol", "sucursal_asignada"])
            messages.success(request, "Empleado actualizado correctamente.")
            return redirect("org:empleados")

        return render(
            request,
            self.template_name,
            {"form": form, "editar": True, "membresia": mem},
        )


class EmpleadoResetPasswordView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    http_method_names = ["post"]

    def post(self, request, pk):
        mem = get_object_or_404(
            EmpresaMembership, pk=pk, empresa=self.empresa_activa
        )
        if mem.is_owner:
            raise PermissionDenied(
                "No se puede resetear la contraseña del propietario.")

        user = mem.user
        user.set_password("temporal123")  # TODO: generar aleatoria + notificar
        user.save()
        messages.info(request, f"Contraseña reseteada para {user.email}.")
        return redirect("org:empleados")


class EmpleadoToggleActivoView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    http_method_names = ["post"]

    def post(self, request, pk):
        mem = get_object_or_404(
            EmpresaMembership, pk=pk, empresa=self.empresa_activa
        )

        if mem.is_owner:
            raise PermissionDenied("No se puede deshabilitar al propietario.")
        if mem.user_id == request.user.id and mem.activo:
            raise PermissionDenied(
                "No podés deshabilitar tu propia membresía activa.")

        mem.activo = not mem.activo
        mem.save(update_fields=["activo"])

        user = mem.user
        if not mem.activo:
            tiene_otras_activas = EmpresaMembership.objects.filter(
                user=user, activo=True
            ).exists()
            if not tiene_otras_activas and user.is_active:
                user.is_active = False
                user.save(update_fields=["is_active"])
        else:
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])

        msg = "habilitado" if mem.activo else "deshabilitado"
        messages.success(request, f"{mem.user.email} fue {msg}.")
        return redirect("org:empleados")


class EmpleadoDestroyUserView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.ORG_EMPLEADOS_MANAGE,)
    http_method_names = ["post"]

    def post(self, request, pk):
        mem = get_object_or_404(
            EmpresaMembership, pk=pk, empresa=self.empresa_activa
        )

        if mem.is_owner:
            raise PermissionDenied("No se puede eliminar al propietario.")
        if mem.user_id == request.user.id:
            raise PermissionDenied("No podés eliminarte a vos mismo.")

        user = mem.user
        email = user.email

        _logout_user_everywhere(user)
        user.delete()  # cascada: memberships

        messages.success(
            request, f"Se eliminó el usuario {email} del sistema.")
        return redirect("org:empleados")
