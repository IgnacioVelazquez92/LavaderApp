# apps/payments/forms/payment.py
from __future__ import annotations

from decimal import Decimal
from django import forms
from apps.payments.models import MedioPago


class PaymentForm(forms.Form):
    medio = forms.ModelChoiceField(
        queryset=MedioPago.objects.none(), label="Medio de pago")
    monto = forms.DecimalField(min_value=Decimal(
        "0.01"), decimal_places=2, max_digits=12, label="Monto")
    es_propina = forms.BooleanField(
        required=False, initial=False, label="Es propina")
    referencia = forms.CharField(required=False, label="Referencia")
    notas = forms.CharField(
        required=False, widget=forms.Textarea, label="Notas")
    idempotency_key = forms.CharField(
        required=False, max_length=64, label="Clave de idempotencia")

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa  # ← conservar empresa para clean_*
        if empresa:
            self.fields["medio"].queryset = (
                MedioPago.objects.filter(
                    empresa=empresa, activo=True).order_by("nombre")
            )

        # Bootstrap
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.update({"class": "form-check-input"})
            elif isinstance(w, (forms.Select,)):
                w.attrs.update({"class": "form-select"})
            else:
                w.attrs.update({"class": "form-control"})

    def clean_medio(self):
        medio = self.cleaned_data.get("medio")
        if self.empresa and medio and medio.empresa_id != self.empresa.id:
            raise forms.ValidationError(
                "El medio de pago no pertenece a la empresa activa.")
        return medio

    def clean_es_propina(self):
        return bool(self.cleaned_data.get("es_propina", False))
