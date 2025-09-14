# apps/sales/views.py
"""
Vistas server-rendered para el módulo de Ventas.
- Listado, creación, detalle (con ítems) y acciones de estado.
- Todas requieren autenticación y empresa activa en sesión.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, View

from apps.sales.models import Venta, VentaItem
from apps.sales.forms.sale import VentaForm

from apps.sales.services import lifecycle as lifecycle_services
from apps.sales.fsm import VentaEstado
from apps.customers.models import Cliente
from apps.sales.forms.service_select import ServiceSelectionForm

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
    Muestra detalle de la venta, ítems y totales.
    Incluye formulario para agregar ítems.
    """

    model = Venta
    template_name = "sales/detail.html"
    context_object_name = "venta"

    def get_queryset(self):
        return (
            Venta.objects.filter(empresa=self.request.empresa_activa)
            .select_related("cliente", "vehiculo", "sucursal")
            .prefetch_related("items__servicio")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        venta = self.object
        tipo = getattr(venta.vehiculo, "tipo", None)
        if tipo:
            ctx["services_form"] = ServiceSelectionForm(
                empresa=venta.empresa,
                sucursal=venta.sucursal,
                tipo_vehiculo=tipo,
            )
        else:
            ctx["services_form"] = ServiceSelectionForm()
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
    POST: transiciona la venta a 'terminado'.
    """

    def post(self, request, pk):
        venta = get_object_or_404(
            Venta, pk=pk, empresa=request.empresa_activa
        )
        try:
            lifecycle_services.on_finalizar(venta)
            messages.success(request, "Venta finalizada correctamente.")
        except Exception as e:
            messages.error(request, f"No se pudo finalizar: {e}")
        return redirect("sales:detail", pk=venta.pk)


class CancelarVentaView(LoginRequiredMixin, View):
    """
    POST: transiciona la venta a 'cancelado'.
    """

    def post(self, request, pk):
        venta = get_object_or_404(
            Venta, pk=pk, empresa=request.empresa_activa
        )
        try:
            lifecycle_services.on_cancelar(venta)
            messages.success(request, "Venta cancelada.")
        except Exception as e:
            messages.error(request, f"No se pudo cancelar: {e}")
        return redirect("sales:detail", pk=venta.pk)
