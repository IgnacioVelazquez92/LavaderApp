# apps/sales/views.py
"""
Vistas server-rendered para el módulo de Ventas.
- Listado, creación, detalle (con ítems) y acciones de estado.
- Todas requieren autenticación y empresa activa en sesión.
"""
from __future__ import annotations
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, View

from apps.sales.models import Venta, VentaItem
from apps.sales.forms.sale import VentaForm

from apps.sales.services import lifecycle as lifecycle_services
from apps.sales.fsm import VentaEstado, puede_transicionar
from apps.customers.models import Cliente
from apps.sales.forms.service_select import ServiceSelectionForm
from apps.notifications.models import PlantillaNotif, Canal
from apps.sales.services import sales as sales_services
from apps.sales.services import items as items_services


# --------------------------------------------------
# Listado de Ventas
# --------------------------------------------------


class VentaListView(LoginRequiredMixin, ListView):
    """
    Lista todas las ventas de la empresa activa.
    Permite filtrar por estado, sucursal y rango de fechas (via GET).
    """

    model = Venta
    template_name = "sales/list.html"
    context_object_name = "ventas"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Venta.objects.filter(empresa=self.request.empresa_activa)
            .select_related("cliente", "vehiculo", "sucursal")
            .order_by("-creado")
        )

        estado = self.request.GET.get("estado")
        if estado:
            qs = qs.filter(estado=estado)

        sucursal_id = self.request.GET.get("sucursal")
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)

        # TODO: filtro rango fechas si se necesita
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Para el filtro opcional de sucursales del template
        if getattr(self.request, "empresa_activa", None):
            ctx["sucursales"] = self.request.empresa_activa.sucursales.all()
        return ctx


# --------------------------------------------------
# Crear Venta
# --------------------------------------------------

class VentaCreateView(LoginRequiredMixin, CreateView):
    """
    Alta de venta con flujo natural:
    1) GET: elegir cliente (auto-submit) → se filtran vehículos.
    2) GET: elegir vehículo (auto-submit) → aparecen servicios disponibles (checkboxes).
    3) POST: crear venta + ítems seleccionados. Sucursal = sucursal_activa.
    """
    model = Venta
    form_class = VentaForm
    template_name = "sales/create.html"

    # Prefija valores en el form GET
    def get_initial(self):
        initial = super().get_initial()
        if cid := self.request.GET.get("cliente"):
            initial["cliente"] = cid
        if vid := self.request.GET.get("vehiculo"):
            initial["vehiculo"] = vid
        return initial

    # Pasa empresa/cliente_id al form para filtrar querysets
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        empresa = getattr(self.request, "empresa_activa", None)
        cliente_id = self.request.GET.get(
            "cliente") or self.request.POST.get("cliente")
        kwargs.update({"empresa": empresa, "cliente_id": cliente_id})
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = getattr(self.request, "empresa_activa", None)
        sucursal = getattr(self.request, "sucursal_activa", None)

        cliente_id = self.request.GET.get("cliente")
        vehiculo_id = self.request.GET.get("vehiculo")

        from apps.customers.models import Cliente
        from apps.vehicles.models import Vehiculo

        cliente_obj = None
        vehiculo_obj = None
        if empresa and cliente_id:
            cliente_obj = Cliente.objects.filter(
                empresa=empresa, activo=True, pk=cliente_id
            ).first()
        if empresa and vehiculo_id:
            vehiculo_obj = Vehiculo.objects.filter(
                empresa=empresa, activo=True, pk=vehiculo_id
            ).select_related("tipo").first()

        ctx["cliente_seleccionado"] = cliente_obj
        ctx["vehiculo_seleccionado"] = vehiculo_obj

        # services_form según contexto
        if empresa and sucursal and vehiculo_obj:
            services_form = ServiceSelectionForm(
                empresa=empresa,
                sucursal=sucursal,
                tipo_vehiculo=vehiculo_obj.tipo,
            )
        else:
            services_form = ServiceSelectionForm()

        ctx["services_form"] = services_form

        # Flag para habilitar el botón "Crear venta"
        field = services_form.fields.get("servicios")
        tiene_servicios = bool(field and getattr(field, "choices", []))

        ctx["crear_habilitado"] = bool(
            cliente_obj and vehiculo_obj and tiene_servicios)

        return ctx

    def post(self, request, *args, **kwargs):
        empresa = getattr(request, "empresa_activa", None)
        sucursal = getattr(request, "sucursal_activa", None)
        if not (empresa and sucursal):
            messages.error(
                request, "Debes seleccionar una sucursal antes de crear una venta.")
            return redirect("org:sucursales")

        # Bind del form base
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)

        cliente = form.cleaned_data["cliente"]
        vehiculo = form.cleaned_data["vehiculo"]

        # Bind del form de servicios con el contexto correcto
        services_form = ServiceSelectionForm(
            request.POST, empresa=empresa, sucursal=sucursal, tipo_vehiculo=vehiculo.tipo
        )
        if not services_form.is_valid():
            # Re-render con errores
            context = self.get_context_data(form=form)
            context["services_form"] = services_form
            return self.render_to_response(context)

        # Crear venta
        venta = sales_services.crear_venta(
            empresa=empresa,
            sucursal=sucursal,
            cliente=cliente,
            vehiculo=vehiculo,
            creado_por=request.user,
            notas=form.cleaned_data.get("notas", ""),
        )

        # Agregar ítems seleccionados
        servicios_ids = [int(sid)
                         for sid in services_form.cleaned_data["servicios"]]
        errores = items_services.agregar_items_batch(
            venta=venta, servicios_ids=servicios_ids)
        if errores:
            messages.warning(
                request, "Algunos servicios no se pudieron agregar: " + " | ".join(errores))

        messages.success(request, "Venta creada en estado borrador.")
        return redirect("sales:detail", pk=venta.pk)

# --------------------------------------------------
# Detalle de Venta
# --------------------------------------------------


class VentaDetailView(LoginRequiredMixin, DetailView):
    """
    Muestra el detalle de la venta, sus ítems, pagos y acciones disponibles.

    Decisiones:
    - **Tenancy**: filtra siempre por `request.empresa_activa`.
    - **UI/UX**: expone en el contexto TODOS los flags/urls que necesita el template,
      para no meter lógica en HTML.

    Contexto expuesto (además de `venta`):
      - `services_form`: formulario para agregar servicios válidos para el tipo de vehículo.
      - `venta_items`: lista de ítems de la venta (con `servicio` precargado).
      - `pagos`: lista de pagos (con `medio` precargado si está disponible).
      - `venta_pagada`: bool (estado == PAGADO).
      - `tiene_comprobante`: bool (existe relación one-to-one).
      - `comprobante_id`: UUID o `None`.
      - `puede_emitir_comprobante`: bool (pagada y sin comprobante).
      - `saldo_cubierto`: bool (saldo_pendiente == 0).
      - `debe_finalizar_para_emitir`: bool (edge legacy: saldo==0 pero no pagada).
      - `puede_finalizar_trabajo`: bool (FSM permite pasar a TERMINADO).

      # Notificaciones (WhatsApp)
      - `has_whatsapp_templates`: hay plantillas activas de WhatsApp en la empresa.
      - `can_notify`: bool → venta TERMINADO **y** hay plantillas WA activas.
      - `notify_url`: URL a `notifications:send_from_sale` con el `venta_id`.
      - `notify_disabled_reason`: string para tooltip cuando el CTA está deshabilitado.
    """

    model = Venta
    template_name = "sales/detail.html"
    context_object_name = "venta"

    def get_queryset(self):
        """
        Filtra por empresa activa y precarga relaciones para evitar N+1.
        """
        return (
            Venta.objects.filter(empresa=self.request.empresa_activa)
            .select_related(
                "cliente",
                "vehiculo",
                "vehiculo__tipo",
                "sucursal",
                "comprobante",  # OneToOneField en Comprobante con related_name="comprobante"
            )
            .prefetch_related(
                "items__servicio",  # related_name="items" (o fallback abajo)
                # related_name="pagos" en Pago (si no, fallback abajo)
                "pagos",
            )
        )

    def get_context_data(self, **kwargs):
        from django.urls import reverse  # import local para mantener snippet autocontenido
        # Selector de notificaciones importado localmente para evitar dependencias globales
        from apps.notifications import selectors as notif_selectors

        ctx = super().get_context_data(**kwargs)
        venta = self.object

        # ---------- Form para agregar servicios ----------
        tipo = getattr(venta.vehiculo, "tipo", None)
        if tipo:
            ctx["services_form"] = ServiceSelectionForm(
                empresa=venta.empresa,
                sucursal=venta.sucursal,
                tipo_vehiculo=tipo,
            )
        else:
            ctx["services_form"] = ServiceSelectionForm()

        # ---------- Ítems ----------
        items_mgr = getattr(venta, "items", None) or getattr(
            venta, "ventaitem_set", None)
        ctx["venta_items"] = list(items_mgr.select_related(
            "servicio").all()) if items_mgr else []

        # ---------- Pagos ----------
        pagos_mgr = getattr(venta, "pagos", None) or getattr(
            venta, "pago_set", None)
        if pagos_mgr:
            try:
                ctx["pagos"] = list(pagos_mgr.select_related("medio").all())
            except Exception:
                ctx["pagos"] = list(pagos_mgr.all())
        else:
            ctx["pagos"] = []

        # ---------- Flags de comprobantes / FSM ----------
        comprobante = getattr(venta, "comprobante", None)
        venta_pagada = (venta.estado == VentaEstado.PAGADO)
        tiene_comprobante = bool(comprobante)
        saldo_cubierto = (getattr(venta, "saldo_pendiente", None) == 0)
        puede_finalizar_trabajo = puede_transicionar(
            venta.estado, VentaEstado.TERMINADO)

        ctx.update({
            "venta_pagada": venta_pagada,
            "tiene_comprobante": tiene_comprobante,
            "comprobante_id": (comprobante.id if tiene_comprobante else None),
            "puede_emitir_comprobante": (venta_pagada and not tiene_comprobante),
            "saldo_cubierto": saldo_cubierto,
            "debe_finalizar_para_emitir": (saldo_cubierto and not venta_pagada),
            "puede_finalizar_trabajo": puede_finalizar_trabajo,
        })

        # ---------- Notificaciones (WhatsApp) ----------
        empresa = getattr(self.request, "empresa_activa", None)
        has_wa_tpl = False
        if empresa:
            # ¿Hay plantillas WA activas para esta empresa?
            has_wa_tpl = notif_selectors.plantillas_activas_whatsapp(
                empresa.id).exists()

        can_notify = (venta.estado == VentaEstado.TERMINADO) and has_wa_tpl
        notify_url = reverse("notifications:send_from_sale",
                             kwargs={"venta_id": str(venta.id)})

        reasons = []
        if venta.estado != VentaEstado.TERMINADO:
            reasons.append("La venta no está en estado TERMINADO.")
        if not has_wa_tpl:
            reasons.append(
                "No hay plantillas de WhatsApp activas en la empresa.")
        ctx.update({
            "has_whatsapp_templates": has_wa_tpl,
            "can_notify": can_notify,
            "notify_url": notify_url,
            "notify_disabled_reason": " ".join(reasons) if reasons else "",
        })

        return ctx


# --------------------------------------------------
# Ítems: agregar, actualizar, eliminar
# --------------------------------------------------


class AgregarItemView(LoginRequiredMixin, View):
    """
    POST: agrega un ítem a la venta (servicio + cantidad).
    """

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa_activa)

        form = ServiceSelectionForm(
            request.POST,
            empresa=venta.empresa,
            sucursal=venta.sucursal,
            tipo_vehiculo=venta.vehiculo.tipo if venta.vehiculo else None,
        )
        if not form.is_valid():
            messages.error(request, "Revisá la selección de servicios.")
            return redirect("sales:detail", pk=venta.pk)

        servicios_ids = [int(sid) for sid in form.cleaned_data["servicios"]]
        errores = items_services.agregar_items_batch(
            venta=venta, servicios_ids=servicios_ids)

        if errores:
            messages.warning(
                request, "Algunos servicios no se pudieron agregar: " + " | ".join(errores))
        else:
            messages.success(request, "Servicios agregados correctamente.")
        return redirect("sales:detail", pk=venta.pk)


class ActualizarItemView(LoginRequiredMixin, View):
    """
    POST: actualiza cantidad de un ítem.
    """

    def post(self, request, pk, item_id):
        venta = get_object_or_404(
            Venta, pk=pk, empresa=request.empresa_activa
        )
        item = get_object_or_404(VentaItem, pk=item_id, venta=venta)
        cantidad = request.POST.get("cantidad")
        try:
            cantidad = int(cantidad)
            items_services.actualizar_cantidad(item=item, cantidad=cantidad)
            messages.success(request, "Cantidad actualizada.")
        except Exception as e:
            messages.error(request, f"No se pudo actualizar: {e}")
        return redirect("sales:detail", pk=venta.pk)


class EliminarItemView(LoginRequiredMixin, View):
    """
    POST: elimina un ítem de la venta.
    """

    def post(self, request, pk, item_id):
        venta = get_object_or_404(
            Venta, pk=pk, empresa=request.empresa_activa
        )
        item = get_object_or_404(VentaItem, pk=item_id, venta=venta)
        try:
            items_services.quitar_item(item=item)
            messages.success(request, "Ítem eliminado.")
        except Exception as e:
            messages.error(request, f"No se pudo eliminar: {e}")
        return redirect("sales:detail", pk=venta.pk)


# --------------------------------------------------
# Acciones de ciclo de vida: finalizar, cancelar
# --------------------------------------------------
class FinalizarVentaView(LoginRequiredMixin, View):
    """
    POST: Finaliza una venta.
    - Recalcula totales y saldo.
    - Si saldo > 0 => estado TERMINADO.
    - Si saldo == 0 => estado TERMINADO + luego PAGADO.
    """

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa_activa)
        try:
            sales_services.finalizar_trabajo(venta=venta, actor=request.user)
            messages.success(request, "Trabajo finalizado.")
        except Exception as e:
            messages.error(request, f"No se pudo finalizar: {e}")
        return redirect("sales:detail", pk=venta.pk)


class CancelarVentaView(LoginRequiredMixin, View):
    """
    POST: transiciona la venta a 'cancelado'.
    """

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa_activa)
        try:
            venta = sales_services.cancelar_venta(venta=venta)  # ← sin actor
            venta.refresh_from_db()  # validación inmediata
            messages.success(request, "Venta cancelada.")
        except Exception as e:
            messages.error(request, f"No se pudo cancelar: {e}")
        return redirect("sales:detail", pk=venta.pk)
