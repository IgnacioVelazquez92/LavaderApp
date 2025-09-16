# apps/invoicing/forms/invoice.py

from __future__ import annotations
from django import forms
from apps.invoicing.models import ClienteFacturacion, TipoComprobante


class InvoiceEmitForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=TipoComprobante.choices,
        initial=TipoComprobante.TICKET,
    )
    punto_venta = forms.IntegerField(
        min_value=1, max_value=9999, initial=1,
        help_text="Punto de venta (1–9999)."
    )
    cliente_facturacion = forms.ModelChoiceField(
        queryset=ClienteFacturacion.objects.none(),
        required=False,
        help_text="Opcional: usar un perfil de facturación alternativo.",
    )

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Bootstrap helpers
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(field.widget,
                                            forms.Select) else "form-control"
            )
        if empresa is not None:
            self.fields["cliente_facturacion"].queryset = ClienteFacturacion.objects.filter(
                empresa=empresa, activo=True
            )
