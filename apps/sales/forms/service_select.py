# apps/sales/forms/service_select.py
from django import forms
from django.db.models import Q
from django.utils.timezone import now

from apps.catalog.models import Servicio
from apps.pricing.models import PrecioServicio


class ServiceSelectionForm(forms.Form):
    """
    Checkbox de servicios válidos para (empresa, sucursal, tipo_vehículo).
    Sin cantidades: cada servicio se agrega una sola vez.
    """
    servicios = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Servicios disponibles",
    )

    def __init__(self, *args, empresa=None, sucursal=None, tipo_vehiculo=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Bootstrap básico en checkboxes
        self.fields["servicios"].widget.attrs.update(
            {"class": "form-check-input"})

        if not (empresa and sucursal and tipo_vehiculo):
            self.fields["servicios"].choices = []
            return

        hoy = now().date()
        servicios_ids = (
            PrecioServicio.objects
            .filter(
                empresa=empresa,
                sucursal=sucursal,
                tipo_vehiculo=tipo_vehiculo,
                activo=True,
                vigencia_inicio__lte=hoy,
            )
            .filter(Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=hoy))
            .values_list("servicio_id", flat=True)
        )
        qs = (Servicio.objects
              .filter(empresa=empresa, activo=True, id__in=list(servicios_ids))
              .order_by("nombre"))

        self.fields["servicios"].choices = [(s.id, s.nombre) for s in qs]
