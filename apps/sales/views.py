# apps/sales/views.py
"""
Vistas server-rendered para el módulo de Ventas.
- Listado, creación, detalle (con ítems) y acciones de estado.
- Todas requieren autenticación y empresa activa en sesión.
- Seguridad: permisos granulares por rol (admin/operador) usando EmpresaPermRequiredMixin.
  * Fuente de verdad: apps.org.permissions.Perm + ROLE_POLICY
  * Helper: has_empresa_perm(user, empresa, perm)
  * Para CBVs: EmpresaPermRequiredMixin con required_perms = (Perm.X, ...)
- Tenancy: el queryset SIEMPRE filtra por empresa=self.empresa_activa
- UI: los templates se apoyan en flags de permiso (puede_crear, puede_editar, etc.)
- Estado operativo (proceso) separado del estado de pago:
  * Proceso (FSM): borrador | en_proceso | terminado | cancelado
  * Pago (payment_status): no_pagada | parcial | pagada
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, View

from apps.sales.models import Venta, VentaItem
from apps.sales.forms.sale import VentaForm
from apps.sales.fsm import VentaEstado, puede_transicionar
from apps.sales.forms.service_select import ServiceSelectionForm
from apps.sales.services import sales as sales_services
from apps.sales.services import items as items_services

# === Permisos/Tenancy (NO mezclar con LoginRequiredMixin) ===
from apps.org.permissions import (
    EmpresaPermRequiredMixin,
    Perm,
    has_empresa_perm,
)


# --------------------------------------------------
# Listado de Ventas
# --------------------------------------------------
class VentaListView(EmpresaPermRequiredMixin, ListView):
    """
    Lista todas las ventas de la empresa activa.
    Permite filtrar por estado, sucursal y rango de fechas (via GET).

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_VIEW,)
    Tenancy:
      - get_queryset filtra por empresa=self.empresa_activa
    UI:
      - ctx["sucursales"] para filtro por sucursal
      - ctx["puede_crear"] para mostrar botón "Nueva venta"
      - ctx["puede_iniciar"], ctx["puede_finalizar"], ctx["puede_cancelar"]
        para acciones rápidas en la lista
    """
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
        # TODO: filtro rango fechas si se necesita
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        user = self.request.user

        if emp:
            ctx["sucursales"] = emp.sucursales.all()

        # Flags de permiso para la UI
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
    """
    Alta de venta con flujo natural:
    1) GET: elegir cliente (auto-submit) → se filtran vehículos.
    2) GET: elegir vehículo (auto-submit) → aparecen servicios disponibles (checkboxes).
    3) POST: crear venta + ítems seleccionados. Sucursal = sucursal_activa.

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_CREATE,)
    Tenancy:
      - empresa = self.empresa_activa
      - sucursal = request.sucursal_activa (middleware)
    UI:
      - ctx["cliente_seleccionado"], ctx["vehiculo_seleccionado"]
      - ctx["services_form"], ctx["crear_habilitado"]
      - ctx["puede_crear"] para el CTA principal
    """
    required_perms = (Perm.SALES_CREATE,)

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
        cliente_id = self.request.GET.get(
            "cliente") or self.request.POST.get("cliente")
        kwargs.update({"empresa": self.empresa_activa,
                      "cliente_id": cliente_id})
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa = self.empresa_activa
        sucursal = getattr(self.request, "sucursal_activa", None)

        # Objetos seleccionados (si aplica)
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

        # Form de servicios (checkboxes) contextualizado
        if empresa and sucursal and vehiculo_obj:
            services_form = ServiceSelectionForm(
                empresa=empresa, sucursal=sucursal, tipo_vehiculo=vehiculo_obj.tipo
            )
        else:
            services_form = ServiceSelectionForm()
        ctx["services_form"] = services_form

        # Flag para habilitar el botón "Crear venta"
        field = services_form.fields.get("servicios")
        tiene_servicios = bool(field and getattr(field, "choices", []))
        ctx["crear_habilitado"] = bool(
            cliente_obj and vehiculo_obj and tiene_servicios)

        # Flags de permiso
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
class VentaDetailView(EmpresaPermRequiredMixin, DetailView):
    """
    Muestra el detalle de la venta, sus ítems, pagos y acciones disponibles.

    Decisiones:
    - Tenancy: filtra siempre por `empresa=self.empresa_activa`.
    - UI/UX: expone en el contexto TODOS los flags/urls que necesita el template,
      para no meter lógica en HTML.

    Contexto expuesto (además de `venta`):
      - `services_form`: formulario para agregar servicios válidos para el tipo de vehículo
         (excluye servicios ya agregados).
      - `venta_items`: lista de ítems de la venta (con `servicio` precargado).
      - `pagos`: lista de pagos (con `medio` precargado si está disponible).
      - `venta_pagada`: bool (payment_status == "pagada").
      - `tiene_comprobante`: bool (existe relación one-to-one).
      - `comprobante_id`: UUID o `None`.
      - `puede_emitir_comprobante`: bool (pagada y sin comprobante).
      - `saldo_cubierto`: bool (saldo_pendiente == 0).
      - `debe_finalizar_para_emitir`: bool (edge: saldo==0 pero aún no pagada).
      - `puede_iniciar_trabajo`: bool (FSM permite pasar a EN_PROCESO).
      - `puede_finalizar_trabajo`: bool (FSM permite pasar a TERMINADO).

      # Notificaciones (WhatsApp)
      - `has_whatsapp_templates`: hay plantillas activas de WhatsApp en la empresa.
      - `can_notify`: bool → venta TERMINADO **y** hay plantillas WA activas.
      - `notify_url`: URL a `notifications:send_from_sale` con el `venta_id`.
      - `notify_disabled_reason`: string para tooltip cuando el CTA está deshabilitado.

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_VIEW,)
      - Flags de permiso para la UI:
        `puede_crear`, `puede_editar`, `puede_iniciar`, `puede_finalizar`, `puede_cancelar`,
        `puede_agregar_items`, `puede_actualizar_cantidad`, `puede_quitar_items`.
    """
    required_perms = (Perm.SALES_VIEW,)

    model = Venta
    template_name = "sales/detail.html"
    context_object_name = "venta"

    def get_queryset(self):
        """
        Filtra por empresa activa y precarga relaciones para evitar N+1.
        """
        return (
            Venta.objects.filter(empresa=self.empresa_activa)
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
        # Importes locales para no depender del módulo completo
        from django.urls import reverse
        from apps.notifications import selectors as notif_selectors

        ctx = super().get_context_data(**kwargs)
        venta = self.object

        # ---------- Form para agregar servicios ----------
        # Pasamos `venta=venta` para que el form EXCLUYA servicios ya agregados.
        tipo = getattr(venta.vehiculo, "tipo", None)
        if tipo:
            ctx["services_form"] = ServiceSelectionForm(
                empresa=venta.empresa,
                sucursal=venta.sucursal,
                tipo_vehiculo=tipo,
                venta=venta,  # ← importante: evita duplicados
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

        # ---------- Flags de comprobantes / FSM / Pago ----------
        comprobante = getattr(venta, "comprobante", None)
        venta_pagada = (getattr(venta, "payment_status", None) == "pagada")
        tiene_comprobante = bool(comprobante)
        saldo_cubierto = (getattr(venta, "saldo_pendiente", None) == 0)
        puede_iniciar_trabajo = puede_transicionar(
            venta.estado, VentaEstado.EN_PROCESO)
        puede_finalizar_trabajo = puede_transicionar(
            venta.estado, VentaEstado.TERMINADO)

        ctx.update({
            "venta_pagada": venta_pagada,
            "tiene_comprobante": tiene_comprobante,
            "comprobante_id": (comprobante.id if tiene_comprobante else None),
            "puede_emitir_comprobante": (venta_pagada and not tiene_comprobante),
            "saldo_cubierto": saldo_cubierto,
            # Edge (raro si payments sincroniza): saldo 0 pero payment_status aún no 'pagada'
            "debe_finalizar_para_emitir": (saldo_cubierto and not venta_pagada),
            "puede_iniciar_trabajo": puede_iniciar_trabajo,
            "puede_finalizar_trabajo": puede_finalizar_trabajo,
        })

        # ---------- Notificaciones (WhatsApp) ----------
        empresa = self.empresa_activa
        has_wa_tpl = notif_selectors.plantillas_activas_whatsapp(
            empresa.id).exists() if empresa else False
        can_notify = (venta.estado == VentaEstado.TERMINADO) and has_wa_tpl

        reasons = []
        if venta.estado != VentaEstado.TERMINADO:
            reasons.append("La venta no está en estado TERMINADO.")
        if not has_wa_tpl:
            reasons.append(
                "No hay plantillas de WhatsApp activas en la empresa.")

        ctx.update({
            "has_whatsapp_templates": has_wa_tpl,
            "can_notify": can_notify,
            "notify_url": reverse("notifications:send_from_sale", kwargs={"venta_id": str(venta.id)}),
            "notify_disabled_reason": " ".join(reasons) if reasons else "",
        })

        # ---------- Flags UI por permiso ----------
        u, emp = self.request.user, empresa
        ctx["puede_crear"] = has_empresa_perm(u, emp, Perm.SALES_CREATE)
        ctx["puede_editar"] = has_empresa_perm(u, emp, Perm.SALES_EDIT)
        # reutilizamos SALES_EDIT para iniciar
        ctx["puede_iniciar"] = has_empresa_perm(u, emp, Perm.SALES_EDIT)
        ctx["puede_finalizar"] = has_empresa_perm(u, emp, Perm.SALES_FINALIZE)
        ctx["puede_cancelar"] = has_empresa_perm(u, emp, Perm.SALES_CANCEL)
        ctx["puede_agregar_items"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_ADD)
        ctx["puede_actualizar_cantidad"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_UPDATE_QTY)
        ctx["puede_quitar_items"] = has_empresa_perm(
            u, emp, Perm.SALES_ITEM_REMOVE)

        return ctx

# --------------------------------------------------
# Ítems: agregar, actualizar, eliminar
# --------------------------------------------------


class AgregarItemView(EmpresaPermRequiredMixin, View):
    """
    POST: agrega uno o varios ítems a la venta (servicio + cantidad=1 en MVP).

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_ITEM_ADD,)
    Tenancy:
      - venta = get_object_or_404(..., empresa=self.empresa_activa)
    UI:
      - messages de éxito/advertencia/errores
    """
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
                request, "Algunos servicios no se pudieron agregar: " + " | ".join(errores))
        else:
            messages.success(request, "Servicios agregados correctamente.")

        return redirect("sales:detail", pk=venta.pk)


class ActualizarItemView(EmpresaPermRequiredMixin, View):
    """
    POST: actualiza cantidad de un ítem.

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_ITEM_UPDATE_QTY,)
    Tenancy:
      - item está acotado a la venta del tenant activo
    UI:
      - feedback vía messages
    """
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
    """
    POST: elimina un ítem de la venta.

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_ITEM_REMOVE,)
    Tenancy:
      - item está acotado a la venta del tenant activo
    UI:
      - feedback vía messages
    """
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
    """
    POST: inicia el trabajo (borrador -> en_proceso).
    Seguridad/Permisos: uso Perm.SALES_EDIT para no crear un perm nuevo.
    """
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
    """
    POST: finaliza la venta (proceso -> TERMINADO).
    - No depende del pago; cierra edición operativa.
    - La emisión de comprobante depende de payment_status='pagada'.

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_FINALIZE,)
    """
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
    """
    POST: transiciona la venta a 'cancelado'.

    Regla por defecto:
      - No permite cancelar si hay pagos (payment_status != 'no_pagada').

    Seguridad/Permisos:
      - required_perms = (Perm.SALES_CANCEL,)
    """
    required_perms = (Perm.SALES_CANCEL,)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        try:
            venta = sales_services.cancelar_venta(
                venta=venta)  # ← sin actor por ahora
            venta.refresh_from_db()  # validación inmediata
            messages.success(request, "Venta cancelada.")
        except Exception as e:
            messages.error(request, f"No se pudo cancelar: {e}")
        return redirect("sales:detail", pk=venta.pk)
