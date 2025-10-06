# apps/cashbox/forms/closure.py
from __future__ import annotations

from django import forms


class _BootstrapFormMixin:
    """
    Inyecta clases Bootstrap a todos los widgets.
    - <select> -> form-select
    - otros -> form-control
    - checkboxes -> form-check-input
    """

    def _apply_bootstrap(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{css} form-check-input".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{css} form-select".strip()
            else:
                css = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{css} form-control".strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class OpenCashboxForm(_BootstrapFormMixin, forms.Form):
    """
    Form de **apertura** de turno/caja.
    **No** permite ingresar fecha/hora: se toma automáticamente en el service (timezone.now()).
    """
    notas = forms.CharField(
        required=False,
        label="Notas",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Notas u observaciones del turno..."}
        ),
        help_text="Opcional. Útil para aclarar novedades del turno.",
    )


class CloseCashboxForm(_BootstrapFormMixin, forms.Form):
    """
    Form de **cierre** de turno/caja.
    **No** permite ingresar fecha/hora: se toma automáticamente en el service (timezone.now()).
    """
    notas_append = forms.CharField(
        required=False,
        label="Notas",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Notas de cierre (diferencias, arqueo, incidencias, etc.)",
            }
        ),
        help_text="Se agregará al final de las notas existentes del turno.",
    )
    confirmar = forms.BooleanField(
        required=True,
        initial=False,
        label="Confirmo el cierre del turno",
        help_text="Marcá esta casilla para confirmar el cierre.",
    )

    def clean_confirmar(self):
        ok = self.cleaned_data.get("confirmar")
        if not ok:
            raise forms.ValidationError(
                "Debés confirmar para cerrar el turno.")
        return ok
