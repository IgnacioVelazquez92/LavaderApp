
# apps/sales/views_promotions.py

from __future__ import annotations
from apps.sales.services import discounts as discount_services
from apps.sales.forms.discounts import (
    OrderDiscountForm,
    ItemDiscountForm,
    ApplyPromotionForm,
)
from apps.sales.models import Venta, VentaItem, SalesAdjustment, Promotion

from django.views import View

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, View, DeleteView

from apps.org.permissions import EmpresaPermRequiredMixin, Perm, has_empresa_perm
from apps.sales.models import Promotion
from apps.sales.forms.promotion import PromotionForm


class PromotionListView(EmpresaPermRequiredMixin, ListView):
    required_perms = (getattr(Perm, "PROMO_VIEW", Perm.SALES_EDIT),)

    model = Promotion
    template_name = "sales/promotions/list.html"
    context_object_name = "promos"
    paginate_by = 20

    def get_queryset(self):
        emp = self.empresa_activa
        qs = Promotion.objects.filter(empresa=emp).select_related(
            "sucursal").order_by("-activo", "-prioridad", "nombre")

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))

        estado = self.request.GET.get("estado")
        if estado == "activas":
            qs = qs.filter(activo=True)
        elif estado == "inactivas":
            qs = qs.filter(activo=False)

        suc = self.request.GET.get("sucursal")
        if suc:
            qs = qs.filter(Q(sucursal_id=suc) | Q(sucursal__isnull=True))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = self.empresa_activa
        u = self.request.user
        ctx["sucursales"] = emp.sucursales.all() if emp else []
        ctx["puede_crear"] = has_empresa_perm(
            u, emp, getattr(Perm, "PROMO_CREATE", Perm.SALES_EDIT))
        ctx["puede_editar"] = has_empresa_perm(
            u, emp, getattr(Perm, "PROMO_EDIT", Perm.SALES_EDIT))
        ctx["puede_borrar"] = has_empresa_perm(
            u, emp, getattr(Perm, "PROMO_DELETE", Perm.SALES_EDIT))
        return ctx


class PromotionCreateView(EmpresaPermRequiredMixin, CreateView):
    required_perms = (getattr(Perm, "PROMO_CREATE", Perm.SALES_EDIT),)

    model = Promotion
    form_class = PromotionForm
    template_name = "sales/promotions/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        return kwargs

    def form_valid(self, form):
        promo = form.save(commit=False)
        promo.empresa = self.empresa_activa
        promo.save()
        messages.success(self.request, "Promoción creada.")
        return redirect("sales:promos_list")


class PromotionUpdateView(EmpresaPermRequiredMixin, UpdateView):
    required_perms = (getattr(Perm, "PROMO_EDIT", Perm.SALES_EDIT),)

    model = Promotion
    form_class = PromotionForm
    template_name = "sales/promotions/form.html"
    context_object_name = "promo"

    def get_queryset(self):
        return Promotion.objects.filter(empresa=self.empresa_activa)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.empresa_activa
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Promoción actualizada.")
        return redirect("sales:promos_list")


class PromotionDeleteView(EmpresaPermRequiredMixin, DeleteView):
    required_perms = (getattr(Perm, "PROMO_DELETE", Perm.SALES_EDIT),)

    model = Promotion
    template_name = "sales/promotions/confirm_delete.html"
    context_object_name = "promo"
    success_url = reverse_lazy("sales:promos_list")

    def get_queryset(self):
        return Promotion.objects.filter(empresa=self.empresa_activa)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Promoción eliminada.")
        return super().delete(request, *args, **kwargs)


class PromotionToggleActiveView(EmpresaPermRequiredMixin, View):
    """
    Activar/Desactivar (soft) una promo.
    """
    required_perms = (getattr(Perm, "PROMO_EDIT", Perm.SALES_EDIT),)

    def post(self, request, pk):
        promo = get_object_or_404(
            Promotion, pk=pk, empresa=self.empresa_activa)
        promo.activo = not promo.activo
        promo.save(update_fields=["activo", "actualizado"])
        messages.success(
            request, f"Promoción {'activada' if promo.activo else 'desactivada'}.")
        return redirect("sales:promos_list")


# --------------------------------------------------
# Descuentos / Promociones
# --------------------------------------------------
class DiscountCreateOrderView(EmpresaPermRequiredMixin, View):
    """
    Aplica un descuento MANUAL a nivel venta.
    """
    required_perms = (getattr(Perm, "SALES_DISCOUNT_ADD", Perm.SALES_EDIT),)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        form = OrderDiscountForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisá los datos del descuento.")
            return redirect("sales:detail", pk=venta.pk)
        try:
            discount_services.agregar_descuento_manual_venta(
                venta=venta,
                mode=form.cleaned_data["mode"],
                value=form.cleaned_data["value"],
                motivo=form.cleaned_data.get("motivo") or "Descuento manual",
                actor=request.user,
            )
            messages.success(request, "Descuento aplicado a la venta.")
        except Exception as e:
            messages.error(request, f"No se pudo aplicar el descuento: {e}")
        return redirect("sales:detail", pk=venta.pk)


class DiscountCreateItemView(EmpresaPermRequiredMixin, View):
    """
    Aplica un descuento MANUAL a nivel ítem.
    """
    required_perms = (getattr(Perm, "SALES_DISCOUNT_ADD", Perm.SALES_EDIT),)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        form = ItemDiscountForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisá los datos del descuento por ítem.")
            return redirect("sales:detail", pk=venta.pk)
        try:
            item = get_object_or_404(
                VentaItem, pk=form.cleaned_data["item_id"], venta=venta
            )
            discount_services.agregar_descuento_manual_item(
                item=item,
                mode=form.cleaned_data["mode"],
                value=form.cleaned_data["value"],
                motivo=form.cleaned_data.get("motivo") or "Descuento manual",
                actor=request.user,
            )
            messages.success(request, "Descuento aplicado al ítem.")
        except Exception as e:
            messages.error(request, f"No se pudo aplicar el descuento: {e}")
        return redirect("sales:detail", pk=venta.pk)


class DiscountDeleteView(EmpresaPermRequiredMixin, View):
    """
    Elimina un ajuste (manual/promo/payment).
    """
    required_perms = (getattr(Perm, "SALES_DISCOUNT_REMOVE", Perm.SALES_EDIT),)

    def post(self, request, pk, adj_id):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        ajuste = get_object_or_404(SalesAdjustment, pk=adj_id, venta=venta)
        try:
            discount_services.eliminar_ajuste(ajuste=ajuste)
            messages.success(request, "Descuento eliminado.")
        except Exception as e:
            messages.error(request, f"No se pudo eliminar el descuento: {e}")
        return redirect("sales:detail", pk=venta.pk)


class PromotionApplyView(EmpresaPermRequiredMixin, View):
    """
    Aplica una promoción vigente (por venta o por ítem).
    Operador permitido (aplicar), admin también.
    """
    required_perms = (getattr(Perm, "SALES_PROMO_APPLY", Perm.SALES_VIEW),)

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, empresa=self.empresa_activa)
        form = ApplyPromotionForm(request.POST)
        if not form.is_valid():
            messages.error(
                request, "Datos inválidos para aplicar la promoción.")
            return redirect("sales:detail", pk=venta.pk)

        try:
            promo = get_object_or_404(
                Promotion,
                pk=form.cleaned_data["promotion_id"],
                empresa=venta.empresa,
            )

            item = None
            if promo.scope == "item":
                item_id = form.cleaned_data.get("item_id")
                if not item_id:
                    messages.error(
                        request, "Seleccione un ítem para esta promoción.")
                    return redirect("sales:detail", pk=venta.pk)
                item = get_object_or_404(VentaItem, pk=item_id, venta=venta)

            discount_services.aplicar_promocion(
                venta=venta,
                promo=promo,
                item=item,
                actor=request.user,  # <- importante para check de permisos en services
            )
            messages.success(request, "Promoción aplicada.")
        except Exception as e:
            messages.error(request, f"No se pudo aplicar la promoción: {e}")
        return redirect("sales:detail", pk=venta.pk)
