# apps/invoicing/views.py
from __future__ import annotations

import mimetypes
from datetime import date
from typing import Any, Dict, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
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
            raise PermissionDenied("No hay empresa activa en la sesión.")
        return empresa

    def get_sucursal_activa(self):
        # No todas las vistas necesitan sucursal; se provee helper por si hace falta
        return getattr(self.request, self.sucursal_attr, None)


class VentaScopedMixin(TenancyRequiredMixin):
    """
    Carga una Venta por `venta_id` (UUID en la URL) y valida que pertenezca a la empresa activa.
    Provee flags de conveniencia para los templates (sin lógica compleja allí).
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
            # Responder 404 para no filtrar existencia cross-tenant
            raise Http404("Venta no encontrada.")
        return venta

    # Helpers para contexto de template (evitar ifs complicados en HTML)
    def get_emit_flags(self, venta: Venta) -> Dict[str, Any]:
        existente = getattr(venta, "comprobante", None)
        return {
            "venta_pagada": getattr(venta, "estado", "") == "pagado",
            "ya_tiene_comprobante": bool(existente),
            "comprobante_existente": existente,
            "puede_emitir": (getattr(venta, "estado", "") == "pagado") and not existente,
        }

# ======================================================================
# Listado y Detalle
# ======================================================================


class ComprobanteListView(LoginRequiredMixin, TenancyRequiredMixin, ListView):
    """
    Listado de comprobantes con filtros por fecha/sucursal/tipo.
    - Siempre filtra por empresa activa (seguridad multi-tenant).
    - Filtros GET (opcionales):
        ?sucursal=<id>
        ?tipo=TICKET|REMITO
        ?desde=YYYY-MM-DD
        ?hasta=YYYY-MM-DD
    """
    model = Comprobante
    template_name = "invoicing/list.html"
    context_object_name = "comprobantes"
    paginate_by = 25

    def get_queryset(self):
        empresa = self.get_empresa_activa()
        # Parse de filtros GET con tolerancia a errores (sin romper la vista)
        sucursal_id = self.request.GET.get("sucursal") or None
        tipo = self.request.GET.get("tipo") or None
        desde = parse_date(self.request.GET.get("desde") or "")
        hasta = parse_date(self.request.GET.get("hasta") or "")

        # FIX: validar sucursal por empresa, sin asumir related_name sucursal_set
        sucursal = None
        if sucursal_id:
            sucursal = Sucursal.objects.filter(
                empresa=empresa, pk=sucursal_id).first()

        # Usamos selector para consistencia
        qs = por_rango(empresa=empresa, sucursal=sucursal,
                       tipo=tipo, desde=desde, hasta=hasta)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.get_empresa_activa()

        # FIX: obtener sucursales por filtro explícito (no usar empresa.sucursal_set)
        sucursales_disponibles = list(
            Sucursal.objects.filter(empresa=empresa).values("id", "nombre")
        )

        # Datos para filtros en template (evita lookups en HTML)
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


class ComprobanteDetailView(LoginRequiredMixin, TenancyRequiredMixin, DetailView):
    """
    Detalle de comprobante con validación de empresa activa.
    """
    model = Comprobante
    template_name = "invoicing/detail.html"
    context_object_name = "comprobante"

    def get_queryset(self):
        empresa = self.get_empresa_activa()
        # Filtra por empresa para no exponer comprobantes de otros tenants
        return (
            Comprobante.objects
            .select_related("empresa", "sucursal", "venta", "cliente", "cliente_facturacion", "emitido_por")
            .filter(empresa=empresa)
        )

# ======================================================================
# Emitir Comprobante (GET form / POST acción)
# ======================================================================


class EmitirComprobanteView(LoginRequiredMixin, VentaScopedMixin, FormView):
    """
    GET: Muestra un form mínimo para seleccionar tipo/punto_venta y (opcional) perfil de facturación.
    POST: Emite el comprobante (idempotente: si ya existe, redirige al existente con mensaje).

    Ruta: /ventas/<uuid:venta_id>/emitir/
    Template: invoicing/emit.html
    """
    template_name = "invoicing/emit.html"
    form_class = InvoiceEmitForm
    success_url = reverse_lazy("invoicing:list")  # fallback

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.get_empresa_activa()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        venta = self.get_venta()
        flags = self.get_emit_flags(venta)
        ctx.update({
            "venta": venta,
            "venta_pagada": flags["venta_pagada"],
            "ya_tiene_comprobante": flags["ya_tiene_comprobante"],
            "comprobante_existente": flags["comprobante_existente"],
            "puede_emitir": flags["puede_emitir"],
        })
        return ctx

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        # Si intenta POST y la venta no está pagada, redirigimos al detalle
        venta = self.get_venta()
        if request.method == "POST":
            if getattr(venta, "estado", "") != "pagado":
                messages.error(request, _(
                    "La venta no está pagada. No se puede emitir el comprobante."))
                return redirect(reverse("sales:detail", kwargs={"pk": str(venta.id)}))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: InvoiceEmitForm):
        venta = self.get_venta()
        tipo = form.cleaned_data["tipo"]

        # Aseguramos entero para numbering
        try:
            punto_venta = int(form.cleaned_data["punto_venta"])
        except (TypeError, ValueError):
            punto_venta = 1

        cf = form.cleaned_data.get("cliente_facturacion")

        try:
            resultado = emitir(
                venta_id=venta.id,
                tipo=tipo,
                punto_venta=punto_venta,
                cliente_facturacion_id=(cf.id if cf else None),
                actor=self.request.user,
                reintentos_idempotentes=True,
            )
        except ValueError as e:
            messages.error(self.request, str(e))
            return redirect(reverse("sales:detail", kwargs={"pk": str(venta.id)}))

        comp = resultado.comprobante

        # Construimos número de forma robusta
        numero = getattr(comp, "numero_completo", None)
        if not numero:
            try:
                numero = f"{int(comp.punto_venta):04d}-{int(comp.numero):08d}"
            except Exception:
                numero = f"{comp.punto_venta}-{comp.numero}"

        if resultado.creado:
            messages.success(self.request, _(
                "Comprobante emitido correctamente: %(n)s") % {"n": numero})
        else:
            messages.info(self.request, _(
                "Esta venta ya tenía un comprobante emitido: %(n)s") % {"n": numero})

        if hasattr(comp, "get_absolute_url") and comp.get_absolute_url():
            self.success_url = comp.get_absolute_url()
        else:
            self.success_url = reverse(
                "invoicing:detail", kwargs={"pk": comp.pk})

        return super().form_valid(form)

# ======================================================================
# Descarga / Visualización del archivo
# ======================================================================


class ComprobanteDownloadView(LoginRequiredMixin, TenancyRequiredMixin, View):
    """
    Sirve el archivo del comprobante:
      - Prefiere PDF si existe; si no, entrega HTML.
      - Valida que el comprobante sea de la empresa activa.
    Ruta: /comprobantes/<uuid:pk>/descargar/
    """

    def get(self, request: HttpRequest, pk: str, *args, **kwargs) -> HttpResponse:
        empresa = self.get_empresa_activa()
        comp = get_object_or_404(
            Comprobante.objects.filter(empresa=empresa),
            pk=pk
        )

        # Selección de archivo a servir
        f = comp.archivo_pdf or comp.archivo_html
        if not f:
            raise Http404("El comprobante no tiene archivo asociado.")

        # content_type por extensión conocida o fallback
        guessed, _ = mimetypes.guess_type(f.name)
        content_type = guessed or (
            "application/pdf" if comp.archivo_pdf else "text/html; charset=utf-8")

        try:
            return FileResponse(f.open("rb"), content_type=content_type, as_attachment=True, filename=f.name.split("/")[-1])
        except FileNotFoundError:
            raise Http404("Archivo no disponible en el almacenamiento.")
