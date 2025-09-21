# apps/cashbox/forms/closure.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django import forms
from django.utils import timezone


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
    Form de **apertura** de cierre de caja.

    Notas:
    - `abierto_en` permite backoffice (p.ej., reabrir según turno); por defecto es ahora.
    - Las entidades de tenant (empresa/sucursal/usuario) NO van en el form: vienen de la request
      y se aplican en el service `abrir_cierre(...)`.
    """

    abierto_en = forms.DateTimeField(
        required=False,
        help_text="Fecha/hora de apertura. Si se deja vacío se usa el momento actual.",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    notas = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Notas u observaciones del turno..."}),
        help_text="Opcional. Útil para aclarar novedades del turno.",
    )

    def clean_abierto_en(self):
        value = self.cleaned_data.get("abierto_en")
        # Si viene como naive (por input), Django lo convertirá con zona del proyecto si USE_TZ=True.
        # Si está vacío, devolvemos None para que el service use timezone.now().
        return value or None


class CloseCashboxForm(_BootstrapFormMixin, forms.Form):
    """
    Form de **cierre** de caja.

    Campos:
    - `cerrado_en`: permite ajustar la marca de tiempo del cierre (default ahora).
    - `confirmar`: casilla obligatoria para evitar cierres por error.
    - `notas_append`: agrega texto a las notas del cierre (no reemplaza).

    Reglas:
    - `confirmar` es obligatorio (UX segura).
    - Validación temporal mínima (el service vuelve a validar y hace check final).
    """

    cerrado_en = forms.DateTimeField(
        required=False,
        help_text="Fecha/hora de cierre. Si se deja vacío se usa el momento actual.",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    notas_append = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Notas de cierre (diferencias, arqueo, incidencias, etc.)",
            }
        ),
        help_text="Se agregará al final de las notas existentes del cierre.",
    )
    confirmar = forms.BooleanField(
        required=True,
        initial=False,
        help_text="Confirmo que revisé los totales y deseo cerrar definitivamente este turno.",
    )

    def clean_cerrado_en(self):
        value = self.cleaned_data.get("cerrado_en")
        return value or None

    def clean_confirmar(self):
        ok = self.cleaned_data.get("confirmar")
        if not ok:
            raise forms.ValidationError(
                "Debes confirmar para cerrar el turno.")
        return ok
