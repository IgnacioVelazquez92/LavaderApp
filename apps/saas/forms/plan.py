# apps/saas/forms/plan.py
"""
Form de PlanSaaS.

Responsabilidad:
- Edición/alta de atributos del plan.
- Aplicar clases Bootstrap a widgets.

No define lógica de unicidad del plan "default" activo (eso se maneja en views/services).
"""

from __future__ import annotations

from django import forms

from ..models import PlanSaaS


class BootstrapFormMixin:
    """
    Inyecta clases Bootstrap 5 a los widgets más comunes.
    Evita repetir clases en cada template.
    """

    def _bs(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.URLInput, forms.Textarea)):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bs()


class PlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PlanSaaS
        fields = (
            "nombre",
            "descripcion",
            "activo",
            "default",
            "trial_days",
            "max_empresas_por_usuario",
            "max_sucursales_por_empresa",
            "max_usuarios_por_empresa",
            "max_empleados_por_sucursal",
            "max_storage_mb",
            "precio_mensual",
            "external_plan_id",
        )
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_trial_days(self):
        v = self.cleaned_data["trial_days"]
        if v < 0:
            raise forms.ValidationError("El trial no puede ser negativo.")
        return v
