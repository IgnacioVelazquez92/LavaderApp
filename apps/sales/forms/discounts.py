# apps/sales/forms/discounts.py
from __future__ import annotations

from decimal import Decimal
from django import forms


def _bootstrapify(form: forms.Form) -> None:
    """
    Aplica clases Bootstrap 5 a todos los campos del form.
    (manteniendo tu guideline de forms bonitos)
    """
    for f in form.fields.values():
        css = f.widget.attrs.get("class", "")
        f.widget.attrs["class"] = (css + " form-control").strip()
    # Ajustes para radios/selects si los usás en el template:
    if "mode" in form.fields:
        form.fields["mode"].widget.attrs["class"] = "form-select"


class _BaseDiscountForm(forms.Form):
    MODE_CHOICES = (("percent", "Porcentaje (%)"), ("amount", "Monto fijo"))

    mode = forms.ChoiceField(choices=MODE_CHOICES, required=True)
    value = forms.DecimalField(
        required=True,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        help_text="Si es porcentaje, use valores 0.01 a 100.00",
    )
    motivo = forms.CharField(
        required=False,
        max_length=160,
        widget=forms.TextInput(
            attrs={"placeholder": "Opcional: nota visible en el ajuste"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean(self):
        cleaned = super().clean()
        mode = (cleaned.get("mode") or "").lower()
        value = cleaned.get("value") or Decimal("0")
        if mode not in {"percent", "amount"}:
            self.add_error(
                "mode", "Modo inválido (debe ser porcentaje o monto).")
        if value <= 0:
            self.add_error("value", "El valor debe ser mayor a 0.")
        if mode == "percent" and value > 100:
            self.add_error("value", "El porcentaje no puede exceder 100%.")
        return cleaned


class OrderDiscountForm(_BaseDiscountForm):
    """
    Descuento manual aplicado a toda la venta.
    """
    pass


class ItemDiscountForm(_BaseDiscountForm):
    """
    Descuento manual aplicado a un ítem específico.
    - El item_id se valida en la vista (pertenencia a la venta).
    """
    item_id = forms.IntegerField(min_value=1, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class ApplyPromotionForm(forms.Form):
    """
    Aplicar una promoción vigente.
    - promotion_id: promoción seleccionada (order o item)
    - item_id: requerido solo si la promo es scope='item' (se valida en la vista)
    """
    promotion_id = forms.IntegerField(min_value=1, required=True)
    item_id = forms.IntegerField(min_value=1, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
