# apps/sales/views.py
"""
Vistas server-rendered para el módulo de Ventas.
- Listado, creación, detalle (con ítems), descuentos y acciones de estado.
- Todas requieren autenticación y empresa activa en sesión.
- Seguridad: permisos granulares por rol usando EmpresaPermRequiredMixin.
- Tenancy: el queryset SIEMPRE filtra por empresa=self.empresa_activa
- UI: los templates se apoyan en flags de permiso (puede_crear, puede_editar, etc.)
- Proceso (FSM) vs Pago: separados.
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, View

from apps.sales.models import Venta, VentaItem, Promotion, SalesAdjustment
from apps.sales.forms.sale import VentaForm
from apps.sales.fsm import VentaEstado, puede_transicionar
from apps.sales.forms.service_select import ServiceSelectionForm
from apps.sales.services import sales as sales_services
from apps.sales.services import items as items_services
from apps.sales.services import discounts as discount_services
from apps.sales.forms.discounts import (
    OrderDiscountForm,
    ItemDiscountForm,
    ApplyPromotionForm,
)

# === Permisos/Tenancy ===
from apps.org.permissions import (
    EmpresaPermRequiredMixin,
    Perm,
    has_empresa_perm,
)

# === Cashbox (turnos) ===
from apps.cashbox.services.guards import SinTurnoAbierto

# --------------------------------------------------
# Listado de Ventas
# --------------------------------------------------


class VentaListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (Perm.SALES_VIEW,)

    model = Venta
    template_name = "sales/list.html"
    context_object_name = "ventas"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Venta.objects.filter(empresa=self.empresa_activa)
            .select_related("cliente", "vehiculo", "sucursal")
            .order_by("-creado")
        )

        estado = self.request.GET.get("estado")
        if estado:
            qs = qs.filter(estado=estado)

        sucursal_id = self.request.GET.get("sucursal")
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)

        pago = self.request.GET.get("pago")
        if pago:
            qs = qs.filter(payment_status=pago)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user

        if emp:
            ctx["sucursales"] = emp.sucursales.all()

        ctx["puede_crear"] = has_empresa_perm(user, emp, Perm.SALES_CREATE)
        ctx["puede_iniciar"] = has_empresa_perm(user, emp, Perm.SALES_EDIT)
        ctx["puede_finalizar"] = has_empresa_perm(
            user, emp, Perm.SALES_FINALIZE)
        ctx["puede_cancelar"] = has_empresa_perm(user, emp, Perm.SALES_CANCEL)
        return ctx


# --------------------------------------------------
# Crear Venta
# --------------------------------------------------
class VentaCreateView(EmpresaPermRequiredMixin, CreateView):
    required_perms = (Perm.SALES_CREATE,)

    model = Venta
    form_class = VentaForm
    template_name = "sales/create.html"

    def get_initial(self):
        initial = super().get_initial()
        if cid := self.request.GET.get("cliente"):
            initial["cliente"] = cid
        if vid := self.request.GET.get("vehiculo"):
            initial["vehiculo"] = vid
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cliente_id = self.request.GET.get(
            "cliente") or self.request.POST.get("cliente")
        kwargs.update({"empresa": self.empresa_activa,
                      "cliente_id": cliente_id})
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa_activa
        sucursal = getattr(self.request, "sucursal_activa", None)

        from apps.customers.models import Cliente
        from apps.vehicles.models import Vehiculo

        cliente_id = self.request.GET.get("cliente")
        vehiculo_id = self.request.GET.get("vehiculo")

        cliente_obj = (
            Cliente.objects.filter(
                empresa=empresa, activo=True, pk=cliente_id).first()
            if (empresa and cliente_id)
            else None
        )
        vehiculo_obj = (
            Vehiculo.objects.filter(
                empresa=empresa, activo=True, pk=vehiculo_id)
            .select_related("tipo")
            .first()
            if (empresa and vehiculo_id)
            else None
        )

        ctx["cliente_seleccionado"] = cliente_obj
        ctx["vehiculo_seleccionado"] = vehiculo_obj

        if empresa and sucursal and vehiculo_obj:
            services_form = ServiceSelectionForm(
                empresa=empresa, sucursal=sucursal, tipo_vehiculo=vehiculo_obj.tipo
            )
        else:
            services_form = ServiceSelectionForm()
        ctx["services_form"] = services_form

        field = services_form.fields.get("servicios")
        tiene_servicios = bool(field and getattr(field, "choices", []))
        ctx["crear_habilitado"] = bool(
            cliente_obj and vehiculo_obj and tiene_servicios)

        ctx["puede_crear"] = has_empresa_perm(
            self.request.user, empresa, Perm.SALES_CREATE)
        return ctx

    def post(self, request, *args, **kwargs):
        empresa = self.empresa_activa
        sucursal = getattr(request, "sucursal_activa", None)
        if not (empresa and sucursal):
            messages.error(
                request, "Debes seleccionar una sucursal antes de crear una venta.")
            return redirect("org:sucursales")

        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)

        cliente = form.cleaned_data["cliente"]
        vehiculo = form.cleaned_data["vehiculo"]

        services_form = ServiceSelectionForm(
            request.POST, empresa=empresa, sucursal=sucursal, tipo_vehiculo=vehiculo.tipo
        )
        if not services_form.is_valid():
            context = self.get_context_data(form=form)
            context["services_form"] = services_form
            return self.render_to_response(context)

        # Crear venta con enforcement de turno
        try:
            venta = sales_services.crear_venta(
                empresa=empresa,
                sucursal=sucursal,
                cliente=cliente,
                vehiculo=vehiculo,
                creado_por=request.user,
                notas=form.cleaned_data.get("notas", ""),
            )
        except SinTurnoAbierto:
            # Redirige a apertura de turno y al volver continúa el flujo (next=)
            messages.warning(
                request,
                "Antes de crear una venta debés abrir un turno de caja para esta sucursal.",
            )
            next_url = request.get_full_path()
            # Ajustá este nombre si tu URL real difiere (ej.: 'cashbox:turno_abrir')
            abrir_url = f"{reverse('cashbox:abrir')}?next={next_url}"
            return redirect(abrir_url)

        servicios_ids = [int(sid)
                         for sid in services_form.cleaned_data["servicios"]]
        errores = items_services.agregar_items_batch(
            venta=venta, servicios_ids=servicios_ids)
        if errores:
            messages.warning(
                request,
                "Algunos servicios no se pudieron agregar: " +
                " | ".join(errores),
            )

        messages.success(request, "Venta creada en estado borrador.")
        return redirect("sales:detail", pk=venta.pk)


# --------------------------------------------------
# Detalle de Venta (incluye descuentos/promos)
# --------------------------------------------------
class VentaDetailView(EmpresaPermRequiredMixin, DetailView):
    required_perms = (Perm.SALES_VIEW,)

    model = Venta
    template_name = "sales/detail.html"
    context_object_name = "venta"

    def get_queryset(self):
        return (
            Venta.objects.filter(empresa=self.empresa_activa)
            .select_related(
                "cliente",
                "vehiculo",
                "vehiculo__tipo",
                "sucursal",
                "comprobante",
            )
            .prefetch_related(
                "items__servicio",
                "pagos",
                "adjustments__item",
                "adjustments__promotion",
            )
        )

    def get_context_data(self, **kwargs):
        from django.urls import reverse
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
                venta=venta,
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

        # ---------- Ajustes (descuentos/promos) ----------
        ajustes = list(venta.adjustments.select_related(
            "item", "promotion").order_by("creado", "id"))
        ctx["ajustes"] = ajustes

        # ---------- Forms para descuentos/promos ----------
        ctx["order_discount_form"] = OrderDiscountForm()
        ctx["item_discount_form"] = ItemDiscountForm()
        ctx["apply_promo_form"] = ApplyPromotionForm()

        # ---------- Promos vigentes ----------
        ctx["promos_order"] = discount_services.listar_promociones_vigentes_para_venta(
            venta=venta)
        ctx["promos_item"] = discount_services.listar_promociones_vigentes_para_item(
            venta=venta)

        # ---------- Flags de comprobantes / FSM / Pago ----------
        comprobante = getattr(venta, "comprobante", None)
        venta_pagada = getattr(venta, "payment_status", None) == "pagada"
        tiene_comprobante = bool(comprobante)
        saldo_cubierto = getattr(venta, "saldo_pendiente", None) == 0
        puede_iniciar_trabajo = puede_transicionar(
            venta.estado, VentaEstado.EN_PROCESO)
        puede_finalizar_trabajo = puede_transicionar(
            venta.estado, VentaEstado.TERMINADO)

        ctx.update(
            {
                "venta_pagada": venta_pagada,
                "tiene_comprobante": tiene_comprobante,
                "comprobante_id": (comprobante.id if tiene_comprobante else None),
                "puede_emitir_comprobante": (venta_pagada and not tiene_comprobante),
                "saldo_cubierto": saldo_cubierto,
                "debe_finalizar_para_emitir": (saldo_cubierto and not venta_pagada),
                "puede_iniciar_trabajo": puede_iniciar_trabajo,
                "puede_finalizar_trabajo": puede_finalizar_trabajo,
            }
        )

        # ---------- Notificaciones (WhatsApp) ----------
        empresa = self.empresa_activa
        has_wa_tpl = (
            notif_selectors.plantillas_activas_whatsapp(
                empresa.id).exists() if empresa else False
        )
        can_notify = (venta.estado == VentaEstado.TERMINADO) and has_wa_tpl

        reasons = []
        if venta.estado != VentaEstado.TERMINADO:
            reasons.append("La venta no está en estado TERMINADO.")
        if not has_wa_tpl:
            reasons.append(
                "No hay plantillas de WhatsApp activas en la empresa.")

        ctx.update(
            {
                "has_whatsapp_templates": has_wa_tpl,
                "can_notify": can_notify,
                "notify_url": reverse(
                    "notifications:send_from_sale", kwargs={"venta_id": str(venta.id)}
                ),
                "notify_disabled_reason": " ".join(reasons) if reasons else "",
            }
        )

        # ---------- Flags UI por permiso ----------
        u, emp = self.request.user, empresa
        ctx["puede_crear"] = has_empresa_perm(u, emp, Perm.SALES_CREATE)
        ctx["puede_editar"] = has_empresa_perm(u, emp, Perm.SALES_EDIT)
        ctx["puede_iniciar"] = has_empresa_perm(u, emp, Perm.SALES_EDIT)
        ctx["puede_finalizar"] = has_empresa_perm(u, emp, Perm.SALES_FINALIZE)
        ctx["puede_cancelar"] = has_empresa_perm(u, emp, Perm.SALES_CANCEL)
        ctx["puede_agregar_items"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_ADD)
        ctx["puede_actualizar_cantidad"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_UPDATE_QTY)
        ctx["puede_quitar_items"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_REMOVE)

        # ---------- Permisos de descuentos ----------
        ctx["puede_agregar_descuento"] = has_empresa_perm(
            u, emp, getattr(Perm, "SALES_DISCOUNT_ADD", Perm.SALES_EDIT)
        )
        ctx["puede_quitar_descuento"] = has_empresa_perm(
            u, emp, getattr(Perm, "SALES_DISCOUNT_REMOVE", Perm.SALES_EDIT)
        )
        ctx["puede_aplicar_promo"] = has_empresa_perm(
            u, emp, getattr(Perm, "SALES_PROMO_APPLY", Perm.SALES_VIEW)
        )
        # ---------- Estado de edición de descuentos ----------
        ctx["descuentos_habilitados"] = venta.estado in (
            "borrador", "en_proceso")

        # ---------- Permisos de gestión de promociones ----------
        ctx["puede_gestionar_promos"] = has_empresa_perm(
            u, emp, getattr(Perm, "PROMO_VIEW", Perm.SALES_EDIT)
        )
        ctx["promos_list_url"] = reverse("sales:promos_list")

        return ctx

# --------------------------------------------------
# Ítems: agregar, actualizar, eliminar
# --------------------------------------------------


class AgregarItemView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_ITEM_ADD,)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)

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
                request, "Algunos servicios no se pudieron agregar: " +
                " | ".join(errores)
            )
        else:
            messages.success(request, "Servicios agregados correctamente.")

        return redirect("sales:detail", pk=venta.pk)


class ActualizarItemView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_ITEM_UPDATE_QTY,)

    def post(self, request, pk, item_id):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        item = get_object_or_404(VentaItem, pk=item_id, venta=venta)
        cantidad = request.POST.get("cantidad")
        try:
            cantidad_int = int(cantidad)
            items_services.actualizar_cantidad(
                item=item, cantidad=cantidad_int)
            messages.success(request, "Cantidad actualizada.")
        except Exception as e:
            messages.error(request, f"No se pudo actualizar: {e}")
        return redirect("sales:detail", pk=venta.pk)


class EliminarItemView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_ITEM_REMOVE,)

    def post(self, request, pk, item_id):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        item = get_object_or_404(VentaItem, pk=item_id, venta=venta)
        try:
            items_services.quitar_item(item=item)
            messages.success(request, "Ítem eliminado.")
        except Exception as e:
            messages.error(request, f"No se pudo eliminar: {e}")
        return redirect("sales:detail", pk=venta.pk)


# --------------------------------------------------
# Acciones de ciclo de vida: iniciar, finalizar, cancelar
# --------------------------------------------------
class IniciarVentaView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_EDIT,)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        try:
            sales_services.iniciar_trabajo(venta=venta, actor=request.user)
            messages.success(request, "Trabajo iniciado (EN PROCESO).")
        except Exception as e:
            messages.error(request, f"No se pudo iniciar el trabajo: {e}")
        return redirect("sales:detail", pk=venta.pk)


class FinalizarVentaView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_FINALIZE,)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        try:
            sales_services.finalizar_trabajo(venta=venta, actor=request.user)
            messages.success(request, "Trabajo finalizado.")
        except Exception as e:
            messages.error(request, f"No se pudo finalizar: {e}")
        return redirect("sales:detail", pk=venta.pk)


class CancelarVentaView(EmpresaPermRequiredMixin, View):
    required_perms = (Perm.SALES_CANCEL,)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        try:
            venta = sales_services.cancelar_venta(venta=venta)
            venta.refresh_from_db()
            messages.success(request, "Venta cancelada.")
        except Exception as e:
            messages.error(request, f"No se pudo cancelar: {e}")
        return redirect("sales:detail", pk=venta.pk)
