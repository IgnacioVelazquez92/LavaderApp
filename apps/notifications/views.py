# apps/notifications/views.py
"""
Vistas de apps.notifications

Incluye:
- CRUD de PlantillaNotif (List/Create/Update).
- Enviar notificación desde una venta (GET/POST).
- Preview de plantilla.
- (Opcional) listado de logs.

Convenciones:
- Tenancy: se filtra por request.empresa_activa en todos los QuerySets.
- Seguridad: en MVP verificamos autenticación + pertenencia de venta/plantilla a la empresa.
- Estados habilitantes: SOLO se permite enviar cuando venta.estado == "terminado"
  (la validación principal vive en dispatcher.enviar_desde_venta()).

Templates esperados (según la doc que compartiste):
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
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, FormView
from .forms import TemplateForm, SendFromSaleForm, PreviewForm
from .models import PlantillaNotif, LogNotif, Canal
from .services import dispatcher, renderers
from . import selectors


# --------------------------
# Mixins utilitarios (MVP)
# --------------------------
class EmpresaContextMixin:
    """Inyecta empresa_activa en self.empresa y en el contexto."""

    empresa_attr_name = "empresa_activa"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.empresa = getattr(request, self.empresa_attr_name, None)
        if not self.empresa:
            raise PermissionDenied("No hay empresa activa en la sesión.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["empresa"] = self.empresa
        return ctx


class RoleGuardMixin:
    """
    Guardado para permisos “suaves” en MVP.
    - allow_manage_templates: quién puede crear/editar plantillas (default: todos los autenticados).
    - allow_send_notifications: quién puede enviar (default: todos los autenticados).
    Cambiá estos métodos cuando tengas el módulo de permisos finos.
    """

    def allow_manage_templates(self, request: HttpRequest) -> bool:
        # MVP: permitir a cualquier autenticado; tu comment indicó “sería solo admin”,
        # pero lo dejamos abierto para ajustar luego.
        return request.user.is_authenticated

    def allow_send_notifications(self, request: HttpRequest) -> bool:
        return request.user.is_authenticated


# --------------------------
# CRUD Plantillas
# --------------------------
class TemplateListView(LoginRequiredMixin, EmpresaContextMixin, RoleGuardMixin, ListView):
    model = PlantillaNotif
    template_name = "notifications/templates_list.html"
    context_object_name = "plantillas"
    paginate_by = 20

    def get_queryset(self):
        qs = PlantillaNotif.objects.filter(
            empresa=self.empresa).order_by("clave")
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

    def dispatch(self, request, *args, **kwargs):
        if not self.allow_manage_templates(request):
            raise PermissionDenied("No tenés permisos para ver plantillas.")
        return super().dispatch(request, *args, **kwargs)


class TemplateCreateView(LoginRequiredMixin, EmpresaContextMixin, RoleGuardMixin, CreateView):
    model = PlantillaNotif
    template_name = "notifications/template_form.html"
    form_class = TemplateForm
    success_url = reverse_lazy("notifications:templates_list")

    def dispatch(self, request, *args, **kwargs):
        if not self.allow_manage_templates(request):
            raise PermissionDenied("No tenés permisos para crear plantillas.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        kwargs["creado_por"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Plantilla creada con éxito."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)


class TemplateUpdateView(LoginRequiredMixin, EmpresaContextMixin, RoleGuardMixin, UpdateView):
    model = PlantillaNotif
    template_name = "notifications/template_form.html"
    form_class = TemplateForm
    success_url = reverse_lazy("notifications:templates_list")

    def dispatch(self, request, *args, **kwargs):
        if not self.allow_manage_templates(request):
            raise PermissionDenied("No tenés permisos para editar plantillas.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Tenancy
        return PlantillaNotif.objects.filter(empresa=self.empresa)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        kwargs["creado_por"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Cambios guardados."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)


# --------------------------
# Enviar desde venta
# --------------------------


class SendFromSaleView(LoginRequiredMixin, RoleGuardMixin, FormView):
    """
    GET: formulario con plantillas ACTIVAS de WhatsApp + destinatario prellenado.
    POST: renderiza, registra Log 'preparado' y muestra botón 'Abrir WhatsApp Web'.
    """
    template_name = "notifications/send_from_sale.html"
    form_class = SendFromSaleForm

    def dispatch(self, request, *args, **kwargs):
        if not self.allow_send_notifications(request):
            raise PermissionDenied(
                "No tenés permisos para enviar notificaciones.")

        empresa = getattr(request, "empresa_activa", None)
        if not empresa:
            raise PermissionDenied("No hay empresa activa en la sesión.")
        self.empresa = empresa

        from apps.sales.models import Venta  # evitar ciclos
        self.venta = get_object_or_404(Venta, pk=kwargs.get("venta_id"))
        if self.venta.empresa_id != self.empresa.id:
            raise PermissionDenied(
                "La venta no pertenece a la empresa activa.")

        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("sales:detail", kwargs={"pk": str(self.venta.id)})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # SOLO plantillas WhatsApp
        qs_plantillas = selectors.plantillas_activas_whatsapp(self.empresa.id)

        # destinatario sugerido: teléfono WhatsApp del cliente
        cliente = getattr(self.venta, "cliente", None)
        initial_dest = getattr(cliente, "tel_wpp", "") or ""

        kwargs.update({
            "empresa": self.empresa,
            "venta": self.venta,
            "queryset_plantillas": qs_plantillas,
            "initial_destinatario": initial_dest,
        })
        return kwargs

    def form_valid(self, form: SendFromSaleForm):
        from .models import Canal, EstadoEnvio  # usar enums reales

        plantilla: PlantillaNotif = form.cleaned_data["plantilla"]
        destinatario = form.cleaned_data["destinatario"]
        nota_extra = form.cleaned_data.get("nota_extra") or ""
        idempotency_key = form.cleaned_data.get("idempotency_key") or ""

        # 1) Render (tu renderer devuelve RenderResult / dict / str)
        render_out = renderers.render(
            plantilla=plantilla,
            venta=self.venta,
            extras={"nota_extra": nota_extra} if nota_extra else {},
        )
        # Normalizá a texto
        if hasattr(render_out, "cuerpo"):
            cuerpo_renderizado = render_out.cuerpo
            asunto_renderizado = getattr(render_out, "asunto", "") or ""
        elif isinstance(render_out, dict):
            cuerpo_renderizado = render_out.get("cuerpo", "")
            asunto_renderizado = render_out.get("asunto", "")
        else:
            cuerpo_renderizado = str(render_out)
            asunto_renderizado = ""

        # 2) Deep link para WhatsApp Web (tolerante a bytes/str)
        wa_url = dispatcher.build_whatsapp_web_url(
            destinatario, cuerpo_renderizado)

        # 3) Registrar Log como 'enviado' (MVP simulado)
        try:
            LogNotif.objects.create(
                id=uuid.uuid4(),
                empresa=self.empresa,                # <-- requerido por tu modelo
                venta=self.venta,
                plantilla=plantilla,
                canal=Canal.WHATSAPP,
                destinatario=destinatario,
                asunto_renderizado=asunto_renderizado,
                cuerpo_renderizado=cuerpo_renderizado,
                estado=EstadoEnvio.ENVIADO,         # <-- tus choices reales
                error_msg="",
                idempotency_key=idempotency_key,
                meta={"nota_extra": nota_extra, "simulado": True},
                creado_por=self.request.user,
            )
        except Exception as e:
            # Si fallara el log, no rompemos la UX de WhatsApp; mostramos warning.
            messages.warning(self.request, f"No se pudo registrar el log: {e}")

        # 4) Feedback + render con botón a WhatsApp
        messages.success(self.request, "Mensaje preparado para WhatsApp Web.")
        context = self.get_context_data(form=form, venta=self.venta)
        context.update({
            "cuerpo_renderizado": cuerpo_renderizado,
            "wa_url": wa_url,
            "was_prepared": True,
        })
        return self.render_to_response(context)

    def form_invalid(self, form):
        messages.error(self.request, _("Revisá los errores en el formulario."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        """
        Garantiza que 'venta' y flags existan SIEMPRE en el contexto,
        tanto en GET como en POST (éxito o inválido).
        """
        ctx = super().get_context_data(**kwargs)
        # Venta siempre presente (la cargamos en dispatch)
        ctx.setdefault("venta", getattr(self, "venta", None))
        # Flags por defecto para evitar err 500 por variables no definidas
        ctx.setdefault("was_prepared", False)
        ctx.setdefault("wa_url", "")
        ctx.setdefault("cuerpo_renderizado", "")
        return ctx
# --------------------------
# Preview
# --------------------------


class PreviewView(LoginRequiredMixin, EmpresaContextMixin, RoleGuardMixin, FormView):
    """
    Renderiza vista previa de una plantilla.
    Si se provee venta_id válido (y de la empresa), usa datos reales.
    Si no, construye un contexto de muestra (mínimo) sin romper.
    """
    template_name = "notifications/preview.html"
    form_class = PreviewForm

    def dispatch(self, request, *args, **kwargs):
        if not self.allow_manage_templates(request):
            raise PermissionDenied(
                "No tenés permisos para previsualizar plantillas.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa
        kwargs["queryset_plantillas"] = PlantillaNotif.objects.filter(
            empresa=self.empresa).order_by("clave")
        return kwargs

    def form_valid(self, form: PreviewForm):
        plantilla: PlantillaNotif = form.cleaned_data["plantilla"]
        venta_id = (form.cleaned_data.get("venta_id") or "").strip()
        nota_extra = form.cleaned_data.get("nota_extra") or ""

        venta = None
        if venta_id:
            from apps.sales.models import Venta
            venta = get_object_or_404(Venta, pk=venta_id)
            if venta.empresa_id != self.empresa.id:
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
            venta.empresa = self.empresa

            cliente = Dummy()
            cliente.nombre = "Juana"
            cliente.apellido = "Pérez"
            cliente.email = "juana@example.com"
            cliente.tel_wpp = "+5493815550000"

            vehiculo = Dummy()
            vehiculo.patente = "ABC123"
            vehiculo.marca = "Toyota"
            vehiculo.modelo = "Etios"

            sucursal = getattr(self, "request").sucursal_activa
            venta.cliente = cliente
            venta.vehiculo = vehiculo
            venta.sucursal = sucursal

        result = renderers.render(plantilla, venta, extras={
                                  "nota_extra": nota_extra} if nota_extra else None)

        # Pasamos el resultado al template
        ctx = self.get_context_data(form=form)
        ctx.update(
            {
                "plantilla": plantilla,
                "asunto_renderizado": result.asunto,
                "cuerpo_renderizado": result.cuerpo,
                "contexto_usado": result.contexto,
            }
        )
        return self.render_to_response(ctx)


# --------------------------
# (Opcional) Listado de logs
# --------------------------
class LogListView(LoginRequiredMixin, EmpresaContextMixin, RoleGuardMixin, ListView):
    model = LogNotif
    template_name = "notifications/logs_list.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self):
        qs = LogNotif.objects.filter(
            empresa=self.empresa).select_related("venta", "plantilla")
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
