from django import forms
from django.utils.translation import gettext_lazy as _
from apps.sales.models import Promotion


class PromotionForm(forms.ModelForm):
    class Meta:
        model = Promotion
        fields = [
            "nombre", "codigo",
            "scope", "mode", "value",
            "activo", "prioridad",
            "valido_desde", "valido_hasta",
            "sucursal",
            "min_total",
            "payment_method_code",
            "descripcion",
        ]
        widgets = {
            "valido_desde": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "valido_hasta": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "prioridad": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "min_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "payment_method_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "p.ej. DEBITO, EFECTIVO"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "scope": forms.Select(attrs={"class": "form-select"}),
            "mode": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sucursal": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar sucursales por empresa activa
        if empresa is not None:
            self.fields["sucursal"].queryset = empresa.sucursales.all()
        # Ayudas
        self.fields["sucursal"].help_text = _(
            "Opcional. Si se deja vacío, aplica a todas las sucursales de la empresa.")
        self.fields["codigo"].help_text = _(
            "Opcional. Para campañas; visible internamente.")
        self.fields["payment_method_code"].help_text = _(
            "Opcional. Si se setea, solo aplica cuando se paga con ese medio.")
