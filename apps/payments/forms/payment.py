# apps/payments/forms/payment.py
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.payments.models import Pago, MedioPago


class PaymentForm(forms.ModelForm):
    """
    Formulario para registrar un pago sobre una venta.

    - Usa MedioPago (configurable por empresa).
    - Valida monto > 0 (la validación contra saldo/tenant va en el service).
    - Inyecta clases Bootstrap.
    - Requiere que le pasen `empresa` en __init__ para filtrar los medios disponibles.
    """

    class Meta:
        model = Pago
        fields = ["medio", "monto", "es_propina", "referencia", "notas"]

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtrar medios por empresa y activos
        if empresa is not None:
            self.fields["medio"].queryset = MedioPago.objects.filter(
                empresa=empresa, activo=True
            ).order_by("nombre")
        else:
            # Evitar exponer medios fuera de contexto
            self.fields["medio"].queryset = MedioPago.objects.none()

        # Bootstrap 5 clases
        self.fields["medio"].widget.attrs.update(
            {"class": "form-select", "autocomplete": "off"}
        )
        self.fields["monto"].widget.attrs.update(
            {"class": "form-control", "placeholder": "0.00", "inputmode": "decimal"}
        )
        self.fields["es_propina"].widget.attrs.update(
            {"class": "form-check-input"}
        )
        self.fields["referencia"].widget.attrs.update(
            {"class": "form-control",
                "placeholder": _("Ej: ID de transacción")}
        )
        self.fields["notas"].widget.attrs.update(
            {"class": "form-control", "rows": 3}
        )

    def clean_monto(self):
        monto = self.cleaned_data.get("monto")
        if monto is None or monto <= Decimal("0.00"):
            raise ValidationError(_("El monto debe ser mayor a 0."))
        return monto
