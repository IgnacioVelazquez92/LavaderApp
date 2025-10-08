# apps/notifications/views.py
"""
Vistas de apps.notifications

Incluye:
- CRUD de PlantillaNotif (List/Create/Update).
- Enviar notificación desde una venta (GET/POST) [WhatsApp en MVP].
- Preview de plantilla.
- (Opcional) listado de logs.

Refactor de seguridad/tenancy:
- ✅ Usa EmpresaPermRequiredMixin (no mezclar con LoginRequiredMixin).
- ✅ required_perms por vista con Perm.* (fuente de verdad).
- ✅ Filtra por empresa activa y setea flags de permiso en el contexto.
- ✅ La validación “solo ventas TERMINADAS” vive en dispatcher.enviar_desde_venta().

Templates esperados:
- notifications/templates_list.html
- notifications/template_form.html
- notifications/send_from_sale.html
- notifications/preview.html
- notifications/logs_list.html (opcional)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, FormView

from apps.org.permissions import (
    EmpresaPermRequiredMixin,
    Perm,
    has_empresa_perm,
)

from .forms import TemplateForm, SendFromSaleForm, PreviewForm
from .models import PlantillaNotif, LogNotif, Canal
from .services import dispatcher, renderers
from . import selectors
from apps.customers.views import TenancyMixin
from .selectors import has_smtp_activo
# --------------------------
# CRUD Plantillas
# --------------------------


class TemplateListView(EmpresaPermRequiredMixin, ListView):
    """
    Listado de plantillas de la empresa activa.
    Permiso requerido: NOTIF_TEMPLATES_MANAGE (admin).
    """
    required_perms = (Perm.NOTIF_TEMPLATES_MANAGE,)

    model = PlantillaNotif
    template_name = "notifications/templates_list.html"
    context_object_name = "plantillas"
    paginate_by = 20

    def get_queryset(self):
        emp = self.empresa_activa
        qs = PlantillaNotif.objects.filter(empresa=emp).order_by("clave")
        canal = self.request.GET.get("canal")
        # "activos" | "inactivos" | None
        estado = self.request.GET.get("estado")
        if canal in (Canal.EMAIL, Canal.WHATSAPP):
            qs = qs.filter(canal=canal)
        if estado == "activos":
            qs = qs.filter(activo=True)
        elif estado == "inactivos":
            qs = qs.filter(activo=False)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(clave__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user
        # Flags UI
        ctx["empresa"] = emp
        ctx["puede_crear"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        ctx["puede_editar"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        ctx["puede_enviar"] = has_empresa_perm(user, emp, Perm.NOTIF_SEND)
        ctx["puede_ver_logs"] = has_empresa_perm(
            user, emp, Perm.NOTIF_LOGS_VIEW)
        return ctx


class TemplateCreateView(EmpresaPermRequiredMixin, CreateView):
    """
    Alta de plantilla (WhatsApp o Email).
    Permiso requerido: NOTIF_TEMPLATES_MANAGE (admin).
    """
    required_perms = (Perm.NOTIF_TEMPLATES_MANAGE,)

    model = PlantillaNotif
    template_name = "notifications/template_form.html"
    form_class = TemplateForm
    success_url = reverse_lazy("notifications:templates_list")

    def get_initial(self):
        """
        Para nuevas plantillas, default canal = whatsapp.
        Esto permite que el form quite el campo asunto_tpl
        en la primera carga (no aparece nunca para WhatsApp).
        """
        initial = super().get_initial()
        initial.setdefault("canal", Canal.WHATSAPP)
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        kwargs["creado_por"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Plantilla creada con éxito."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user
        ctx["empresa"] = emp
        ctx["puede_crear"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        ctx["puede_editar"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        return ctx


class TemplateUpdateView(EmpresaPermRequiredMixin, UpdateView):
    """
    Edición de plantilla (WhatsApp o Email).
    Permiso requerido: NOTIF_TEMPLATES_MANAGE (admin).
    """
    required_perms = (Perm.NOTIF_TEMPLATES_MANAGE,)

    model = PlantillaNotif
    template_name = "notifications/template_form.html"
    form_class = TemplateForm
    success_url = reverse_lazy("notifications:templates_list")

    def get_queryset(self):
        # Tenancy: aseguramos que solo se pueda editar plantillas de la empresa activa
        return PlantillaNotif.objects.filter(empresa=self.empresa_activa)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        kwargs["creado_por"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Cambios guardados."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user
        ctx["empresa"] = emp
        ctx["puede_crear"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        ctx["puede_editar"] = has_empresa_perm(
            user, emp, Perm.NOTIF_TEMPLATES_MANAGE)
        return ctx

# --------------------------
# Enviar desde venta (WhatsApp en MVP)
# --------------------------


class SendFromSaleView(EmpresaPermRequiredMixin, TenancyMixin, FormView):
    """
    GET: formulario con plantillas ACTIVAS (email y whatsapp) + sugerencias de destinatario por canal.
    POST: usa dispatcher.enviar_desde_venta() (valida estado=terminado),
          registra Log y:
            - canal=email   -> envía real por SMTP y redirige con mensaje de éxito.
            - canal=whatsapp-> prepara deep link y renderiza preview en la misma página.
    """
    required_perms = (Perm.NOTIF_SEND,)
    template_name = "notifications/send_from_sale.html"
    form_class = SendFromSaleForm

    # ----------------------
    # Helpers internos
    # ----------------------
    def _venta_queryset(self):
        # Import local para evitar ciclos
        from apps.sales.models import Venta
        return Venta.objects.filter(empresa=self.empresa)

    # ----------------------
    # Lifecycle
    # ----------------------
    def dispatch(self, request, *args, **kwargs):
        self.venta = get_object_or_404(
            self._venta_queryset(), pk=kwargs.get("venta_id"))
        # Seguridad tenant extra (por si alguien cambia el mixin)
        if self.venta.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "La venta no pertenece a la empresa activa.")
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        # Volvemos al detalle de venta; ajustá si tu ruta difiere
        return reverse("sales:detail", kwargs={"pk": str(self.venta.id)})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # Plantillas ACTIVAS de ambos canales.
        try:
            qs_email = selectors.plantillas_activas_email(self.empresa.id)
            qs_wapp = selectors.plantillas_activas_whatsapp(self.empresa.id)
            qs_plantillas = (qs_email | qs_wapp).order_by("clave")
        except AttributeError:
            # Fallback si tenés un selector único
            qs_plantillas = selectors.plantillas_activas(self.empresa.id)

        # Sugerencias de destinatario por canal
        cliente = getattr(self.venta, "cliente", None)
        suggested_email = (getattr(cliente, "email", "") or "").strip()
        # Usá el campo correcto de tu modelo (tel_wpp / telefono / phone ...)
        suggested_wpp = (getattr(cliente, "tel_wpp", "") or "").strip()

        # Inicial genérica para GET (preferimos email si hay; sino wpp; sino vacío)
        initial_dest = suggested_email or suggested_wpp or ""

        kwargs.update({
            "empresa": self.empresa,
            "venta": self.venta,
            "queryset_plantillas": qs_plantillas,
            "initial_destinatario": initial_dest,
            # Pasamos también los hints por canal para que el template/JS los use
            "suggested_email": suggested_email,
            "suggested_wpp": suggested_wpp,
        })
        return kwargs

    # ----------------------
    # POST OK
    # ----------------------
    def form_valid(self, form: SendFromSaleForm):
        plantilla: PlantillaNotif = form.cleaned_data["plantilla"]
        destinatario = form.cleaned_data["destinatario"]
        nota_extra = form.cleaned_data.get("nota_extra") or ""
        idempotency_key = form.cleaned_data.get("idempotency_key") or ""

        canal = getattr(plantilla, "canal", None)

        # Si es EMAIL y no hay SMTP activo → bloquear con feedback
        if canal == Canal.EMAIL and not has_smtp_activo(self.empresa):
            messages.error(self.request, _(
                "No hay un servidor SMTP activo configurado para esta empresa."))
            return super().form_invalid(form)

        # Orquestación centralizada
        try:
            log = dispatcher.enviar_desde_venta(
                plantilla=plantilla,
                venta=self.venta,
                destinatario=destinatario,
                actor=self.request.user,
                extras={"nota_extra": nota_extra} if nota_extra else None,
                idempotency_key=idempotency_key,
            )
        except dispatcher.NotificationError as e:
            messages.error(self.request, str(e))
            return super().form_invalid(form)
        except Exception:
            messages.error(self.request, _(
                "Ocurrió un error al enviar la notificación."))
            return super().form_invalid(form)

        # Resultado por canal
        estado = (getattr(log, "estado", "") or "").lower()
        if "error" in estado:
            msg = getattr(log, "error_msg", "") or _(
                "No se pudo completar el envío.")
            messages.error(self.request, msg)
            return super().form_invalid(form)

        if canal == Canal.EMAIL:
            messages.success(self.request, _("Email enviado correctamente."))
            return redirect(self.get_success_url())
        else:
            # WhatsApp: deep link en misma página (MVP)
            wa_url = dispatcher.build_whatsapp_web_url(
                log.destinatario, log.cuerpo_renderizado)
            messages.success(self.request, _(
                "Mensaje preparado para WhatsApp Web."))
            context = self.get_context_data(form=form, venta=self.venta)
            context.update({
                "cuerpo_renderizado": log.cuerpo_renderizado,
                "wa_url": wa_url,
                "was_prepared": True,
            })
            return self.render_to_response(context)

    # ----------------------
    # POST inválido
    # ----------------------
    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)

    # ----------------------
    # Contexto común
    # ----------------------
    def get_context_data(self, **kwargs):
        """
        Garantiza 'venta' y flags SIEMPRE en el contexto (GET/POST).
        Agrega bandera smtp_activo y las sugerencias por canal para UX.
        """
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa
        user = self.request.user
        cliente = getattr(self.venta, "cliente", None)

        ctx.setdefault("venta", getattr(self, "venta", None))
        ctx.setdefault("was_prepared", False)
        ctx.setdefault("wa_url", "")
        ctx.setdefault("cuerpo_renderizado", "")

        # Sugerencias por canal disponibles para el template/JS
        ctx["suggested_email"] = (getattr(cliente, "email", "") or "").strip()
        ctx["suggested_wpp"] = (getattr(cliente, "tel_wpp", "") or "").strip()

        ctx["empresa"] = emp
        ctx["puede_enviar"] = has_empresa_perm(user, emp, Perm.NOTIF_SEND)
        ctx["smtp_activo"] = has_smtp_activo(emp)
        ctx["puede_crear_smtp"] = has_empresa_perm(
            user, emp, Perm.NOTIF_SMTP_CREATE)
        return ctx

# --------------------------
# Preview
# --------------------------


class PreviewView(EmpresaPermRequiredMixin, FormView):
    """
    Renderiza vista previa de una plantilla.
    Si se provee venta_id válido (y de la empresa), usa datos reales.
    Si no, construye un contexto de muestra (mínimo) sin romper.
    Permiso: NOTIF_TEMPLATES_MANAGE (admin), ya que expone cuerpo/variables.
    """
    required_perms = (Perm.NOTIF_TEMPLATES_MANAGE,)

    template_name = "notifications/preview.html"
    form_class = PreviewForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        kwargs["queryset_plantillas"] = PlantillaNotif.objects.filter(
            empresa=self.empresa_activa
        ).order_by("clave")
        return kwargs

    def form_valid(self, form: PreviewForm):
        plantilla: PlantillaNotif = form.cleaned_data["plantilla"]
        venta_id = (form.cleaned_data.get("venta_id") or "").strip()
        nota_extra = form.cleaned_data.get("nota_extra") or ""

        venta = None
        if venta_id:
            from apps.sales.models import Venta
            venta = get_object_or_404(Venta, pk=venta_id)
            if venta.empresa_id != self.empresa_activa.id:
                raise PermissionDenied(
                    "La venta no pertenece a la empresa activa.")

        # Si no hay venta, creamos un objeto “falso” mínimo para contexto
        if not venta:
            class Dummy:
                pass

            venta = Dummy()
            venta.id = "UUID-DE-EJEMPLO"
            venta.total = "—"
            venta.estado = "terminado"
            venta.empresa = self.empresa_activa

            cliente = Dummy()
            cliente.nombre = "Juana"
            cliente.apellido = "Pérez"
            cliente.email = "juana@example.com"
            cliente.tel_wpp = "+5493815550000"

            vehiculo = Dummy()
            vehiculo.patente = "ABC123"
            vehiculo.marca = "Toyota"
            vehiculo.modelo = "Etios"

            # sucursal_activa la expone el middleware; si no existe, toleramos
            sucursal = getattr(self.request, "sucursal_activa", None)
            venta.cliente = cliente
            venta.vehiculo = vehiculo
            venta.sucursal = sucursal

        result = renderers.render(
            plantilla,
            venta,
            extras={"nota_extra": nota_extra} if nota_extra else None,
        )

        ctx = self.get_context_data(form=form)
        ctx.update(
            {
                "plantilla": plantilla,
                "asunto_renderizado": result.asunto,
                "cuerpo_renderizado": result.cuerpo,
                "contexto_usado": result.contexto,
                "empresa": self.empresa_activa,
            }
        )
        return self.render_to_response(ctx)


# --------------------------
# (Opcional) Listado de logs
# --------------------------
class LogListView(EmpresaPermRequiredMixin, ListView):
    """
    Listado de logs de notificaciones.
    Permiso: NOTIF_LOGS_VIEW (admin y operador).
    """
    required_perms = (Perm.NOTIF_LOGS_VIEW,)

    model = LogNotif
    template_name = "notifications/logs_list.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self):
        emp = self.empresa_activa
        qs = (
            LogNotif.objects.filter(empresa=emp)
            .select_related("venta", "plantilla")
        )
        canal = self.request.GET.get("canal")
        estado = self.request.GET.get("estado")
        venta_id = (self.request.GET.get("venta") or "").strip()
        desde = (self.request.GET.get("desde") or "").strip()
        hasta = (self.request.GET.get("hasta") or "").strip()

        if canal in (Canal.EMAIL, Canal.WHATSAPP):
            qs = qs.filter(canal=canal)
        if estado in ("enviado", "error"):
            qs = qs.filter(estado=estado)
        if venta_id:
            qs = qs.filter(venta_id=venta_id)
        if desde:
            try:
                d = datetime.fromisoformat(desde)
                qs = qs.filter(enviado_en__gte=d)
            except ValueError:
                pass
        if hasta:
            try:
                h = datetime.fromisoformat(hasta)
                qs = qs.filter(enviado_en__lt=h)
            except ValueError:
                pass

        return qs.order_by("-enviado_en")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user
        ctx["empresa"] = emp
        ctx["puede_ver_logs"] = has_empresa_perm(
            user, emp, Perm.NOTIF_LOGS_VIEW)
        ctx["puede_enviar"] = has_empresa_perm(user, emp, Perm.NOTIF_SEND)
        return ctx
