# apps/pricing/forms/price.py
from __future__ import annotations

from typing import Any
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import PrecioServicio, Moneda
# ⬇️ importa los modelos referenciados para filtrar por empresa
from apps.org.models import Sucursal
from apps.catalog.models import Servicio
from apps.vehicles.models import TipoVehiculo


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
        super().__init__(*args, **kwargs)

        # Guarda el contexto de empresa y setéalo en la instancia para validaciones/save
        self._empresa_ctx = empresa
        if empresa is not None:
            self.instance.empresa = empresa

        # Bootstrap 5
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")

        # Calendario HTML5
        for fname in ("vigencia_inicio", "vigencia_fin"):
            if fname in self.fields:
                w = self.fields[fname].widget
                w.input_type = "date"
                if hasattr(w, "format"):
                    w.format = "%Y-%m-%d"
                w.attrs.setdefault("placeholder", "")

        self.fields["precio"].widget.attrs.setdefault("placeholder", "0,00")

        # Valor por defecto para vigencia_inicio
        if not self.initial.get("vigencia_inicio"):
            self.initial["vigencia_inicio"] = timezone.localdate()

        # ⬇️ FILTROS MULTI-TENANT
        if empresa is not None:
            # Si tenés flag de activo en estos modelos, podés sumar activo=True
            self.fields["sucursal"].queryset = (
                Sucursal.objects.filter(empresa=empresa).order_by("nombre")
            )
            self.fields["servicio"].queryset = (
                Servicio.objects.filter(
                    empresa=empresa, activo=True).order_by("nombre")
            )
            self.fields["tipo_vehiculo"].queryset = (
                TipoVehiculo.objects.filter(
                    empresa=empresa, activo=True).order_by("nombre")
            )

        # ⬇️ En edición: bloquear cambio de combinación (clave lógica)
        if self.instance and self.instance.pk:
            for fld in ("sucursal", "servicio", "tipo_vehiculo"):
                if fld in self.fields:
                    self.fields[fld].disabled = True
                    # Aviso UX
                    self.fields[fld].help_text = (
                        "Este campo no puede editarse. Usá “Duplicar como nuevo” para cambiar la combinación."
                    )

    def clean(self):
        cleaned = super().clean()

        ini = cleaned.get("vigencia_inicio")
        fin = cleaned.get("vigencia_fin")
        if ini and fin and fin < ini:
            self.add_error(
                "vigencia_fin",
                "La fecha 'vigente hasta' no puede ser anterior al 'vigente desde'.",
            )

        empresa = self._empresa_ctx or (
            self.instance and self.instance.empresa)
        sucursal = cleaned.get("sucursal")
        servicio = cleaned.get("servicio")
        tipo = cleaned.get("tipo_vehiculo")

        # ⬇️ COHERENCIA DE EMPRESA (defensa en profundidad)
        if empresa:
            if sucursal and getattr(sucursal, "empresa_id", None) != empresa.id:
                self.add_error(
                    "sucursal", "La sucursal no pertenece a la empresa activa.")
            if servicio and getattr(servicio, "empresa_id", None) != empresa.id:
                self.add_error(
                    "servicio", "El servicio no pertenece a la empresa activa.")
            if tipo and getattr(tipo, "empresa_id", None) != empresa.id:
                self.add_error(
                    "tipo_vehiculo", "El tipo de vehículo no pertenece a la empresa activa.")

        # Ayuda previa contra duplicados exactos en misma fecha de inicio
        if empresa and sucursal and servicio and tipo and ini:
            qs = PrecioServicio.objects.filter(
                empresa=empresa,
                sucursal=sucursal,
                servicio=servicio,
                tipo_vehiculo=tipo,
                vigencia_inicio=ini,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "Ya existe un precio con la misma combinación y 'vigente desde' en esa fecha."
                )

        return cleaned

    def save(self, commit=True):
        obj: PrecioServicio = super().save(commit=False)
        if self._empresa_ctx is not None:
            obj.empresa = self._empresa_ctx
        if commit:
            # full_clean invoca validadores de modelo (seguros ante formularios incompletos)
            obj.full_clean()
            obj.save()
        return obj
