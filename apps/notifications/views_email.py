"""
Vistas para la administración de servidores SMTP (EmailServer).
Separadas de views.py para mantener ordenado el módulo notifications.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from apps.org.permissions import Perm, has_empresa_perm, EmpresaPermRequiredMixin

from apps.customers.views import TenancyMixin

from .models import EmailServer
from .forms.email_server import EmailServerForm
from .services.smtp import test_smtp_connection


class EmailServerListView(EmpresaPermRequiredMixin, TenancyMixin, ListView):
    """
    Lista todos los servidores SMTP configurados en la empresa activa.
    Requiere permiso: NOTIF_SMTP_VIEW
    """
    required_perms = [Perm.NOTIF_SMTP_VIEW]
    model = EmailServer
    template_name = "notifications/emailserver_list.html"
    context_object_name = "items"

    def get_queryset(self):
        # Multi-tenant: solo servidores de la empresa activa
        return EmailServer.objects.filter(empresa=self.empresa)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["puede_crear"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.NOTIF_SMTP_CREATE)
        ctx["puede_editar"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.NOTIF_SMTP_EDIT)
        ctx["puede_eliminar"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.NOTIF_SMTP_DELETE)
        ctx["puede_testear"] = has_empresa_perm(
            self.request.user, self.empresa, Perm.NOTIF_SMTP_TEST)
        return ctx


class EmailServerCreateView(EmpresaPermRequiredMixin, TenancyMixin, CreateView):
    """
    Alta de un nuevo servidor SMTP.
    Requiere permiso: NOTIF_SMTP_CREATE
    """
    required_perms = [Perm.NOTIF_SMTP_CREATE]
    model = EmailServer
    form_class = EmailServerForm
    template_name = "notifications/emailserver_form.html"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.empresa = self.empresa
        obj.save()
        messages.success(self.request, _(
            "Servidor SMTP creado correctamente."))
        return redirect("notifications:emailserver_list")


class EmailServerUpdateView(EmpresaPermRequiredMixin, TenancyMixin, UpdateView):
    """
    Edición de un servidor SMTP existente.
    Requiere permiso: NOTIF_SMTP_EDIT
    """
    required_perms = [Perm.NOTIF_SMTP_EDIT]
    model = EmailServer
    form_class = EmailServerForm
    template_name = "notifications/emailserver_form.html"

    def get_queryset(self):
        return EmailServer.objects.filter(empresa=self.empresa)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Servidor SMTP actualizado."))
        return redirect("notifications:emailserver_list")


class EmailServerDeleteView(EmpresaPermRequiredMixin, TenancyMixin, DeleteView):
    """
    Eliminación de un servidor SMTP.
    Requiere permiso: NOTIF_SMTP_DELETE
    """
    required_perms = [Perm.NOTIF_SMTP_DELETE]
    model = EmailServer
    template_name = "notifications/emailserver_confirm_delete.html"

    def get_queryset(self):
        return EmailServer.objects.filter(empresa=self.empresa)

    def get_success_url(self):
        messages.success(self.request, _("Servidor SMTP eliminado."))
        return reverse("notifications:emailserver_list")


def emailserver_test_connection_view(request, pk):
    empresa = getattr(request, "empresa_activa", None)
    obj = get_object_or_404(EmailServer, pk=pk, empresa=empresa)
    if not has_empresa_perm(request.user, empresa, Perm.NOTIF_SMTP_TEST):
        messages.error(request, _(
            "No tenés permisos para probar este servidor SMTP."))
        return redirect("notifications:emailserver_list")
    if request.method == "POST":
        ok, err = test_smtp_connection(obj)
        if ok:
            messages.success(request, _("Conexión SMTP exitosa."))
        else:
            messages.error(request, _(
                "Falló la conexión SMTP: ") + (err or ""))
        return redirect("notifications:emailserver_test", pk=obj.pk)
    return render(request, "notifications/emailserver_test.html", {"obj": obj})
