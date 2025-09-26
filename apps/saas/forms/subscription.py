# apps/saas/forms/subscription.py
"""
Form de SuscripcionSaaS.

Responsabilidad:
- Alta/edición manual (staff) de suscripciones.
- Aplicar clases Bootstrap a widgets.

Nota:
- No se implementa lógica de cobro aquí (eso vive en services + webhooks).
"""

from __future__ import annotations

from django import forms

from ..models import SuscripcionSaaS


class BootstrapFormMixin:
    def _bs(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.URLInput, forms.Textarea, forms.DateInput)):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bs()


class SubscriptionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SuscripcionSaaS
        fields = (
            "empresa",
            "plan",
            "estado",
            "inicio",
            "fin",
            "payment_status",
            "external_customer_id",
            "external_subscription_id",
            "external_plan_id",
            "last_payment_at",
            "next_billing_at",
        )
        widgets = {
            "inicio": forms.DateInput(attrs={"type": "date"}),
            "fin": forms.DateInput(attrs={"type": "date"}),
        }
