# apps/invoicing/views.py
from __future__ import annotations

import mimetypes
from typing import Any, Dict
from django.utils import timezone
from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.invoicing.forms.invoice import InvoiceEmitForm
from apps.invoicing.models import Comprobante, TipoComprobante
from apps.invoicing.selectors import por_rango
from apps.invoicing.services.emit import emitir
from apps.sales.models import Venta
from apps.org.models import Sucursal
from apps.org.permissions import EmpresaPermRequiredMixin, Perm


# ======================================================================
# Mixins de Tenancy y utilidades
# ======================================================================


class TenancyRequiredMixin:
    """
    Expone request.empresa_activa y request.sucursal_activa con validaciones mínimas.
    Lanza PermissionDenied si faltan (no debería pasar si el middleware está bien).
    """
    empresa_attr = "empresa_activa"
    sucursal_attr = "sucursal_activa"

    def get_empresa_activa(self):
        empresa = getattr(self.request, self.empresa_attr, None)
        if not empresa:
            raise Http404("No hay empresa activa en la sesión.")
        return empresa

    def get_sucursal_activa(self):
        return getattr(self.request, self.sucursal_attr, None)


class VentaScopedMixin(TenancyRequiredMixin):
    """
    Carga una Venta por `venta_id` (UUID en la URL) y valida que pertenezca a la empresa activa.
    Provee flags de conveniencia para los templates.
    """
    venta_url_kwarg = "venta_id"

    def get_venta(self) -> Venta:
        empresa = self.get_empresa_activa()
        venta_id = self.kwargs.get(self.venta_url_kwarg)
        venta = get_object_or_404(
            Venta.objects.select_related(
                "empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo"),
            pk=venta_id,
        )
        if venta.empresa_id != empresa.id:
            raise Http404("Venta no encontrada.")
        return venta

    def get_emit_flags(self, venta: Venta) -> Dict[str, Any]:
        existente = getattr(venta, "comprobante", None)
        return {
            "venta_pagada": getattr(venta, "payment_status", "") == "pagada",
            "ya_tiene_comprobante": bool(existente),
            "comprobante_existente": existente,
            "puede_emitir": (getattr(venta, "payment_status", "") == "pagada") and not existente,
        }

# ======================================================================
# Listado y Detalle
# ======================================================================


class ComprobanteListView(EmpresaPermRequiredMixin, ListView):
    model = Comprobante
    template_name = "invoicing/list.html"
    context_object_name = "comprobantes"
    paginate_by = 25
    required_perms = (Perm.INVOICING_VIEW,)

    def get_queryset(self):
        empresa = self.empresa_activa
        sucursal_id = self.request.GET.get("sucursal") or None
        tipo = self.request.GET.get("tipo") or None
        desde = parse_date(self.request.GET.get("desde") or "")
        hasta = parse_date(self.request.GET.get("hasta") or "")

        sucursal = None
        if sucursal_id:
            sucursal = Sucursal.objects.filter(
                empresa=empresa, pk=sucursal_id).first()

        return por_rango(empresa=empresa, sucursal=sucursal, tipo=tipo, desde=desde, hasta=hasta)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa_activa
        sucursales_disponibles = list(
            Sucursal.objects.filter(empresa=empresa).values("id", "nombre")
        )
        ctx.update({
            "filtros": {
                "sucursal": self.request.GET.get("sucursal") or "",
                "tipo": self.request.GET.get("tipo") or "",
                "desde": self.request.GET.get("desde") or "",
                "hasta": self.request.GET.get("hasta") or "",
            },
            "tipos_disponibles": TipoComprobante.choices,
            "sucursales_disponibles": sucursales_disponibles,
        })
        return ctx


class ComprobanteDetailView(EmpresaPermRequiredMixin, DetailView):
    model = Comprobante
    template_name = "invoicing/detail.html"
    context_object_name = "comprobante"
    required_perms = (Perm.INVOICING_VIEW,)

    def get_queryset(self):
        empresa = self.empresa_activa  # <- antes usaba get_empresa_activa()
        return (
            Comprobante.objects
            .select_related("empresa", "sucursal", "venta", "cliente",
                            "cliente_facturacion", "emitido_por")
            .filter(empresa=empresa)
        )


# ======================================================================
# Emitir Comprobante
# ======================================================================


class EmitirComprobanteView(EmpresaPermRequiredMixin, VentaScopedMixin, FormView):
    """
    GET: Form mínimo para seleccionar tipo y (opcional) perfil de facturación.
    POST: Emite el comprobante (idempotente).
    """
    template_name = "invoicing/emit.html"
    form_class = InvoiceEmitForm
    success_url = reverse_lazy("invoicing:list")
    required_perms = (Perm.INVOICING_EMIT,)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # ahora pasamos la venta, no empresa
        kwargs["venta"] = self.get_venta()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        venta = self.get_venta()
        flags = self.get_emit_flags(venta)
        ctx.update({
            "venta": venta,
            **flags,
        })
        return ctx

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        venta = self.get_venta()
        if request.method == "POST":
            if getattr(venta, "payment_status", "") != "pagada":
                messages.error(request, _("La venta no está pagada."))
                return redirect(reverse("sales:detail", kwargs={"pk": str(venta.id)}))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: InvoiceEmitForm):
        venta = self.get_venta()
        tipo = form.cleaned_data["tipo"]
        cf = form.cleaned_data.get("cliente_facturacion")

        try:
            resultado = emitir(
                venta_id=venta.id,
                tipo=tipo,
                punto_venta=1,  # fijo, ya no viene del form
                cliente_facturacion_id=(cf.id if cf else None),
                actor=self.request.user,
                reintentos_idempotentes=True,
            )
        except ValueError as e:
            messages.error(self.request, str(e))
            return redirect(reverse("sales:detail", kwargs={"pk": str(venta.id)}))

        comp = resultado.comprobante
        numero = getattr(comp, "numero_completo", None)
        if not numero:
            try:
                numero = f"{int(comp.punto_venta):04d}-{int(comp.numero):08d}"
            except Exception:
                numero = f"{comp.punto_venta}-{comp.numero}"

        if resultado.creado:
            messages.success(self.request, _(
                "Comprobante emitido: %(n)s") % {"n": numero})
        else:
            messages.info(self.request, _(
                "Ya existía comprobante: %(n)s") % {"n": numero})

        self.success_url = comp.get_absolute_url() or reverse(
            "invoicing:detail", kwargs={"pk": comp.pk})
        return super().form_valid(form)


# ======================================================================
# Descarga / Visualización
# ======================================================================


# ======================================================================
# Descarga / Visualización
# ======================================================================

class ComprobanteDownloadView(EmpresaPermRequiredMixin, View):
    """
    Descarga privada del comprobante (valida empresa activa + permiso).
    """
    required_perms = (Perm.INVOICING_DOWNLOAD,)

    def get(self, request: HttpRequest, pk: str, *args, **kwargs) -> HttpResponse:
        empresa = self.empresa_activa  # <- usar atributo del mixin
        comp = get_object_or_404(
            Comprobante.objects.filter(empresa=empresa),
            pk=pk
        )

        # Prefiere PDF; si no hay, entrega HTML
        f = comp.archivo_pdf or comp.archivo_html
        if not f:
            raise Http404("El comprobante no tiene archivo.")

        guessed, _ = mimetypes.guess_type(f.name)
        content_type = guessed or (
            "application/pdf" if comp.archivo_pdf else "text/html; charset=utf-8")

        try:
            return FileResponse(
                f.open("rb"),
                content_type=content_type,
                as_attachment=True,
                filename=f.name.split("/")[-1],
            )
        except FileNotFoundError:
            raise Http404("Archivo no disponible.")


class PublicInvoiceView(DetailView):
    """
    Vista pública (sin auth) del comprobante imprimible (A4).
    Valida key pública y expiración/revocación.
    """
    template_name = "invoicing/_invoice_print.html"
    context_object_name = "comprobante"

    def get_object(self, queryset=None):
        key = self.kwargs.get("key")
        comp = get_object_or_404(
            Comprobante.objects.select_related(
                "venta", "sucursal", "empresa", "cliente"),
            public_key=key,
        )
        if comp.public_revocado or (comp.public_expires_at and timezone.now() > comp.public_expires_at):
            raise Http404("Link inválido")
        return comp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["snapshot"] = self.object.snapshot
        ctx["public"] = True
        return ctx


class PublicInvoiceDownloadView(View):
    """
    Descarga pública del comprobante (PDF si existe; si no, HTML).
    """

    def get(self, request, *args, **kwargs):
        key = kwargs.get("key")
        comp = get_object_or_404(Comprobante, public_key=key)

        if comp.public_revocado or (comp.public_expires_at and timezone.now() > comp.public_expires_at):
            raise Http404("Link inválido")

        file_field = comp.archivo_pdf or comp.archivo_html
        if not file_field:
            raise Http404("Sin archivo")

        filename = (
            comp.archivo_pdf and "comprobante.pdf") or "comprobante.html"
        return FileResponse(
            file_field.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf" if comp.archivo_pdf else "text/html; charset=utf-8",
        )
