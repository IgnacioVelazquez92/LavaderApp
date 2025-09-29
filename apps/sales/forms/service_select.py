# apps/sales/forms/service_select.py
from datetime import date
from django import forms
from django.utils import timezone
from django.db import models

from apps.catalog.models import Servicio
from apps.pricing.models import PrecioServicio
from apps.pricing.services import resolver as pricing_resolver
from apps.sales.models import Venta


class ServiceSelectionForm(forms.Form):
    """
    Checkboxes con servicios disponibles (según empresa/sucursal/tipo_vehículo y vigencia de precios).
    - Excluye servicios ya agregados a la venta (si se provee `venta` o `excluir_ids`).
    - Muestra etiqueta con precio resuelto.
    """
    servicios = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )

    def __init__(
        self, *args,
        empresa=None,
        sucursal=None,
        tipo_vehiculo=None,
        fecha: date | None = None,
        venta: Venta | None = None,
        excluir_ids: list[int] | None = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        # Si no hay contexto suficiente, sin choices
        if not (empresa and sucursal and tipo_vehiculo):
            self.fields["servicios"].choices = []
            return

        hoy: date = fecha or timezone.localdate()

        # Servicios activos de la empresa
        servicios_qs = Servicio.objects.filter(
            empresa=empresa, activo=True
        ).order_by("nombre")

        # Filtrar por existencia de precios vigentes
        precios_qs = (
            PrecioServicio.objects.filter(
                empresa=empresa,
                sucursal=sucursal,
                tipo_vehiculo=tipo_vehiculo,
                activo=True,
                vigencia_inicio__lte=hoy,
            )
            .filter(models.Q(vigencia_fin__isnull=True) | models.Q(vigencia_fin__gte=hoy))
        )
        vigentes_ids = list(precios_qs.values_list(
            "servicio_id", flat=True).distinct())
        servicios_qs = servicios_qs.filter(id__in=vigentes_ids)

        # Excluir servicios ya agregados a la venta
        excluir_set = set(excluir_ids or [])
        if venta is not None:
            existentes = venta.items.values_list("servicio_id", flat=True)
            excluir_set.update(existentes)
        if excluir_set:
            servicios_qs = servicios_qs.exclude(id__in=excluir_set)

        # Construir choices con precio
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
                # Si no resolvió precio (raro porque filtramos por vigencia): lo omitimos
                continue

        self.fields["servicios"].choices = choices
