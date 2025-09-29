# apps/sales/forms/item.py
from django import forms
from django.utils.timezone import now
from django.db import models

from apps.sales.models import VentaItem, Venta
from apps.catalog.models import Servicio
from apps.pricing.models import PrecioServicio  # para filtrar por vigencia


class VentaItemForm(forms.ModelForm):
    """
    Form future-proof para agregar/editar un ítem con cantidad.
    - Muestra únicamente servicios con precio vigente
      para (empresa, sucursal de la venta, tipo del vehículo).
    - Excluye servicios ya presentes en la venta (evita duplicados).
    """
    class Meta:
        model = VentaItem
        fields = ["servicio", "cantidad"]

    def __init__(self, *args, venta: Venta | None = None, **kwargs):
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

        # IDs con precio vigente
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

        # Excluir servicios ya agregados a la venta
        existentes = set(venta.items.values_list("servicio_id", flat=True))

        self.fields["servicio"].queryset = (
            Servicio.objects.filter(
                empresa=venta.empresa,
                id__in=servicios_ids,
                activo=True,
            )
            .exclude(id__in=existentes)
            .order_by("nombre")
        )

    def clean_cantidad(self):
        cant = self.cleaned_data.get("cantidad") or 0
        if int(cant) < 1:
            raise forms.ValidationError("La cantidad debe ser al menos 1.")
        return cant
