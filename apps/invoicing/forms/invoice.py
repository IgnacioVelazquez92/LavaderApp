# apps/invoicing/forms/invoice.py
from __future__ import annotations
from django import forms
from apps.customers.models import ClienteFacturacion
from apps.invoicing.models import TipoComprobante


class InvoiceEmitForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=TipoComprobante.choices,
        initial=TipoComprobante.TICKET,
        label="Tipo de comprobante",
    )

    # Campo condicional, se inyecta solo si el cliente tiene datos fiscales cargados
    cliente_facturacion = forms.ModelChoiceField(
        queryset=ClienteFacturacion.objects.none(),
        required=False,
        label="Cliente de facturación",
        help_text="Usar un perfil de facturación alternativo.",
    )

    def __init__(self, *args, venta=None, **kwargs):
        super().__init__(*args, **kwargs)

        # estilos Bootstrap 5
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(field.widget, forms.Select)
                else "form-control"
            )

        # Si se pasa una venta, filtramos el perfil de facturación del cliente
        if venta and hasattr(venta, "cliente"):
            qs = ClienteFacturacion.objects.filter(cliente=venta.cliente)
            if qs.exists():
                self.fields["cliente_facturacion"].queryset = qs
            else:
                # Si no hay datos fiscales → no mostramos el campo
                self.fields.pop("cliente_facturacion", None)
