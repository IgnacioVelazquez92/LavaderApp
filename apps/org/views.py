# apps/org/views.py

from apps.accounts.models import EmpresaMembership
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from .models import Empresa, Sucursal
from .forms.org import EmpresaForm, SucursalForm
from .selectors import empresas_para_usuario


def _set_empresa_activa_automatica(request):
    """ Pone en sesión la única empresa del usuario (si existe). """
    if not request.user.is_authenticated:
        return
    if request.session.get("empresa_id"):
        return
    emp = (Empresa.objects
           .filter(memberships__user=request.user, activo=True)
           .order_by("id")
           .first())
    if emp:
        request.session["empresa_id"] = emp.pk


def _first_empresa_for(user):
    """Devuelve la primera empresa del usuario (o None)."""
    return (Empresa.objects
            .filter(memberships__user=user, activo=True)
            .order_by("id")
            .first())


class EmpresaListView(LoginRequiredMixin, ListView):
    """ Si querés mantener una pantalla de Empresa, solo lectura/edición. """
    model = Empresa
    template_name = "org/empresas.html"
    context_object_name = "empresas"

    def get_queryset(self):
        return Empresa.objects.filter(memberships__user=self.request.user).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # no mostramos “nueva” si ya tiene una
        ctx["puede_crear_empresa"] = False
        return ctx


class EmpresaCreateView(LoginRequiredMixin, CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = "org/empresa_form.html"

    def dispatch(self, request, *args, **kwargs):
        # Límite: 1 empresa por usuario (o el que definas)
        from django.conf import settings
        max_emp = getattr(settings, "SAAS_MAX_EMPRESAS_POR_USUARIO", 1)
        actuales = EmpresaMembership.objects.filter(user=request.user).count()
        if actuales >= max_emp:
            messages.info(
                request, "Ya tenés tu lavadero creado. Podés gestionar sus sucursales.")
            return redirect(reverse("org:sucursales"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Guardar explícito y controlar el redirect nosotros
        self.object = form.save()

        # Crear membresía admin para el creador
        EmpresaMembership.objects.get_or_create(
            user=self.request.user, empresa=self.object, defaults={
                "rol": "admin"}
        )

        # Fijar empresa activa en sesión
        self.request.session["empresa_id"] = self.object.pk

        messages.success(
            self.request, f"¡Lavadero creado! {self.object.nombre}")
        # Onboarding: ir a crear la primera sucursal
        return redirect(reverse("org:sucursal_nueva"))

    def form_invalid(self, form):
        messages.error(
            self.request, "Revisá los campos marcados y volvé a intentar.")
        return super().form_invalid(form)


class EmpresaUpdateView(LoginRequiredMixin, UpdateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = "org/empresa_form.html"
    # evita el mismo problema en edición
    success_url = reverse_lazy("org:empresas")

    def form_valid(self, form):
        messages.success(self.request, "Cambios guardados.")
        return super().form_valid(form)


class SucursalListView(LoginRequiredMixin, ListView):
    model = Sucursal
    template_name = "org/sucursales.html"
    context_object_name = "sucursales"

    def get_queryset(self):
        _set_empresa_activa_automatica(self.request)
        empresa_id = self.request.session.get("empresa_id")
        return Sucursal.objects.filter(empresa_id=empresa_id)


class SucursalCreateView(LoginRequiredMixin, CreateView):
    model = Sucursal
    form_class = SucursalForm
    template_name = "org/sucursal_form.html"
    success_url = reverse_lazy("org:sucursales")  # <- importante

    def _ensure_empresa_activa(self, request):
        _set_empresa_activa_automatica(request)
        return request.session.get("empresa_id")

    def form_valid(self, form):
        empresa_id = self._ensure_empresa_activa(self.request)
        if not empresa_id:
            messages.error(
                self.request, "Primero creá tu lavadero antes de agregar sucursales.")
            return redirect(reverse("org:empresa_nueva"))

        form.instance.empresa_id = empresa_id

        # Guardar normalmente (si algo falla de validación, no entra acá)
        response = super().form_valid(form)

        # Primera sucursal → al panel
        cant = Sucursal.objects.filter(empresa_id=empresa_id).count()
        if cant == 1:
            messages.success(
                self.request, "Sucursal creada. ¡Listo para operar!")
            return redirect(reverse("home"))

        # Resto → a listado
        messages.success(self.request, "Sucursal creada con éxito.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(
            self.request, "Revisá los campos marcados y volvé a intentar.")
        return super().form_invalid(form)


class SelectorEmpresaView(LoginRequiredMixin, View):
    template_name = "org/selector.html"

    def get(self, request):
        empresas = empresas_para_usuario(request.user)
        empresa_id = request.GET.get("empresa")

        # Si vino ?empresa=... → activar explícitamente esa empresa
        if empresa_id:
            return self._activar_y_redirigir(request, empresa_id)

        # Si NO hay empresa activa en sesión, y el usuario tiene al menos una,
        # fijamos por defecto la PRIMERA empresa.
        if not request.session.get("empresa_id"):
            default_emp = _first_empresa_for(request.user)
            if default_emp:
                request.session["empresa_id"] = default_emp.pk

        # Flag de plan (máx. empresas permitidas)
        from django.conf import settings
        max_emp = getattr(settings, "SAAS_MAX_EMPRESAS_POR_USUARIO", 1)
        actuales = EmpresaMembership.objects.filter(user=request.user).count()
        puede_crear_empresa = actuales < max_emp

        return render(request, self.template_name, {
            "empresas": empresas,
            "puede_crear_empresa": puede_crear_empresa,
        })

    def post(self, request):
        # 1) Cambio de sucursal desde el sidebar (no requiere pasar empresa)
        sucursal_id = request.POST.get("sucursal")
        if sucursal_id:
            empresa_id = request.session.get("empresa_id")
            if not empresa_id:
                # Si no hay empresa en sesión, elegimos la primera del usuario
                emp = _first_empresa_for(request.user)
                if not emp:
                    messages.error(request, "Primero creá tu lavadero.")
                    return redirect(reverse("org:empresa_nueva"))
                request.session["empresa_id"] = emp.pk
                empresa_id = emp.pk

            # Validar que la sucursal pertenezca a la empresa activa
            suc = get_object_or_404(
                Sucursal, pk=sucursal_id, empresa_id=empresa_id)
            request.session["sucursal_id"] = suc.pk
            messages.success(request, f"Sucursal activa: {suc.nombre}")
            next_url = request.GET.get("next") or request.POST.get(
                "next") or reverse("home")
            return redirect(next_url)

        # 2) Cambio/selección de empresa (caso planes con >1 empresa)
        empresa_id = request.POST.get("empresa")
        if not empresa_id:
            # Si no viene empresa y tampoco sucursal, usar fallback: primera empresa del usuario
            emp = _first_empresa_for(request.user)
            if not emp:
                messages.error(request, "Primero creá tu lavadero.")
                return redirect(reverse("org:empresa_nueva"))
            # Activamos la primera empresa y redirigimos
            return self._activar_y_redirigir(request, emp.pk)

        return self._activar_y_redirigir(request, empresa_id)

    def _activar_y_redirigir(self, request, empresa_id):
        empresa = get_object_or_404(Empresa, pk=empresa_id, activo=True)

        # Verificar membresía
        es_miembro = EmpresaMembership.objects.filter(
            user=request.user, empresa=empresa).exists()
        if not es_miembro:
            messages.error(request, "No tenés acceso a esta empresa.")
            return redirect(reverse_lazy("org:selector"))

        # Activar empresa
        request.session["empresa_id"] = empresa.pk

        # Si había una sucursal en sesión que no pertenece a esta empresa, la limpiamos
        sucursal_id = request.session.get("sucursal_id")
        if sucursal_id and not Sucursal.objects.filter(pk=sucursal_id, empresa=empresa).exists():
            request.session.pop("sucursal_id", None)

        messages.success(request, f"Empresa activa: {empresa.nombre}")
        next_url = request.GET.get("next") or request.POST.get(
            "next") or reverse("home")
        return redirect(next_url)


class PostLoginRedirectView(LoginRequiredMixin, View):
    """ Después de login/registro: fijar empresa y mandar a lo que sigue. """

    def get(self, request, *args, **kwargs):
        # ¿Tiene empresa?
        tiene = EmpresaMembership.objects.filter(user=request.user).exists()
        if not tiene:
            return redirect(reverse("org:empresa_nueva"))

        # Fijar empresa automáticamente (sin selector ni activar)
        _set_empresa_activa_automatica(request)

        # Si no hay sucursales aún → crear primera
        empresa_id = request.session.get("empresa_id")
        if not empresa_id:
            # si algo falló arriba, mandamos a crear empresa
            return redirect(reverse("org:empresa_nueva"))
        if not Sucursal.objects.filter(empresa_id=empresa_id).exists():
            return redirect(reverse("org:sucursal_nueva"))

        # Listo: al panel
        return redirect(reverse("home"))


class SucursalUpdateView(LoginRequiredMixin, UpdateView):
    model = Sucursal
    form_class = SucursalForm
    template_name = "org/sucursal_form.html"
    success_url = reverse_lazy("org:sucursales")
