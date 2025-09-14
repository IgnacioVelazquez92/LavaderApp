# apps/sales/forms/service_select.py
from datetime import date
from django import forms
from django.utils import timezone

from apps.catalog.models import Servicio
from apps.pricing.models import PrecioServicio
from apps.pricing.services import resolver as pricing_resolver
from django.db import models


class ServiceSelectionForm(forms.Form):
    servicios = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )

    def __init__(self, *args, empresa=None, sucursal=None, tipo_vehiculo=None, fecha=None, **kwargs):
        super().__init__(*args, **kwargs)

        if not (empresa and sucursal and tipo_vehiculo):
            self.fields["servicios"].choices = []
            return

        hoy: date = fecha or timezone.localdate()

        servicios_qs = Servicio.objects.filter(
            empresa=empresa, activo=True
        ).order_by("nombre")

        # Filtrar por existencia de precios vigentes
        precios_qs = PrecioServicio.objects.filter(
            empresa=empresa,
            sucursal=sucursal,
            tipo_vehiculo=tipo_vehiculo,
            activo=True,
            vigencia_inicio__lte=hoy,
        ).filter(
            models.Q(vigencia_fin__isnull=True) | models.Q(
                vigencia_fin__gte=hoy)
        )

        vigentes_ids = list(
            precios_qs.values_list("servicio_id", flat=True).distinct()
        )

        servicios_qs = servicios_qs.filter(id__in=vigentes_ids)

        choices = []
        for srv in servicios_qs:
            precio = pricing_resolver.get_precio_vigente(
                empresa=empresa,
                sucursal=sucursal,
                servicio=srv,
                tipo_vehiculo=tipo_vehiculo,
                fecha=hoy,
            )
            if precio is not None:
                label = f"{srv.nombre} — ${precio.precio}"
                choices.append((str(srv.id), label))
            else:
                print(
                    f"  [WARN] Servicio {srv.id} sin precio resuelto aunque figura vigente")
        self.fields["servicios"].choices = choices
