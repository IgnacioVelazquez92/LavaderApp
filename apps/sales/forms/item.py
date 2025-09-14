# apps/sales/forms/item.py
from django import forms
from django.utils.timezone import now
from apps.sales.models import VentaItem
from apps.catalog.models import Servicio
from apps.pricing.models import PrecioServicio  # para filtrar por vigencia
from django.db import models


class VentaItemForm(forms.ModelForm):
    """
    Muestra únicamente servicios que tienen precio vigente
    para (empresa, sucursal de la venta, tipo del vehículo).
    """
    class Meta:
        model = VentaItem
        fields = ["servicio", "cantidad"]

    def __init__(self, *args, venta=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Bootstrap
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs.update({"class": "form-select"})
            else:
                widget.attrs.update({"class": "form-control"})

        self.fields["cantidad"].widget.attrs.update({"min": 1})
        self.fields["cantidad"].initial = 1

        if venta is None:
            # Sin contexto, no mostramos nada (prevención)
            self.fields["servicio"].queryset = Servicio.objects.none()
            return

        hoy = now().date()
        servicios_ids = (
            PrecioServicio.objects.filter(
                empresa=venta.empresa,
                sucursal=venta.sucursal,
                tipo_vehiculo=venta.vehiculo.tipo,
                activo=True,
                vigencia_inicio__lte=hoy,
            )
            .filter(models.Q(vigencia_fin__isnull=True) | models.Q(vigencia_fin__gte=hoy))
            .values_list("servicio_id", flat=True)
        )

        self.fields["servicio"].queryset = (
            Servicio.objects.filter(
                empresa=venta.empresa, id__in=servicios_ids, activo=True)
            .order_by("nombre")
        )
