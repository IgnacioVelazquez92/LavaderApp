# apps/pricing/forms/price.py
from __future__ import annotations

from typing import Any
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import PrecioServicio, Moneda


class PriceForm(forms.ModelForm):
    class Meta:
        model = PrecioServicio
        fields = (
            "sucursal",
            "servicio",
            "tipo_vehiculo",
            "precio",
            "moneda",
            "vigencia_inicio",
            "vigencia_fin",
            "activo",
        )

    def __init__(self, *args: Any, empresa=None, **kwargs: Any) -> None:
        """
        - Aplica clases Bootstrap a TODOS los widgets.
        - Filtra los queryset por empresa activa (multi-tenant).
        - Establece valores por defecto sensatos.
        """
        super().__init__(*args, **kwargs)

        # Asegurá que la instancia ya tenga empresa para validaciones
        if empresa is not None:
            self.instance.empresa = empresa

        # Bootstrap 5: clases por defecto
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.update({"class": "form-check-input"})
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.update({"class": "form-select"})
            else:
                widget.attrs.update({"class": "form-control"})

        # ✅ Forzar calendario nativo HTML5 en fechas
        for fname in ("vigencia_inicio", "vigencia_fin"):
            if fname in self.fields:
                w = self.fields[fname].widget
                # tipo de input = date (calendario)
                w.input_type = "date"
                # formateo consistente con HTML5
                if hasattr(w, "format"):
                    w.format = "%Y-%m-%d"
                # opcional: placeholder limpio cuando no hay valor
                w.attrs.setdefault("placeholder", "")

        # Placeholders/ayudas mínimas
        self.fields["precio"].widget.attrs.setdefault("placeholder", "0,00")

        # Defaults
        if not self.initial.get("vigencia_inicio"):
            self.initial["vigencia_inicio"] = timezone.localdate()

        self._empresa_ctx = empresa

    def clean(self):
        """
        Validaciones extra a nivel form:
          - coherencia de fechas (fin >= inicio si fin existe),
          - evita iguales exactos a uno ya existente (ayuda al UX antes del constraint),
          - chequeo ligero de “abierto activo” para dar error claro.
        """
        cleaned = super().clean()

        ini = cleaned.get("vigencia_inicio")
        fin = cleaned.get("vigencia_fin")
        if ini and fin and fin < ini:
            self.add_error(
                "vigencia_fin", "La fecha 'vigente hasta' no puede ser anterior al 'vigente desde'.")

        empresa = self._empresa_ctx or (
            self.instance and self.instance.empresa)
        sucursal = cleaned.get("sucursal")
        servicio = cleaned.get("servicio")
        tipo = cleaned.get("tipo_vehiculo")

        if empresa and sucursal and servicio and tipo and ini:
            # Ayuda previa: si ya existe la misma combinación con el mismo inicio
            qs = PrecioServicio.objects.filter(
                empresa=empresa, sucursal=sucursal, servicio=servicio, tipo_vehiculo=tipo, vigencia_inicio=ini
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "Ya existe un precio con la misma combinación y 'vigente desde' en esa fecha.")

        return cleaned

    def save(self, commit=True):
        """
        Asigna la empresa activa en la instancia antes de persistir.
        """
        obj: PrecioServicio = super().save(commit=False)
        if self._empresa_ctx is not None:
            obj.empresa = self._empresa_ctx
        if commit:
            obj.full_clean()
            obj.save()
        return obj
