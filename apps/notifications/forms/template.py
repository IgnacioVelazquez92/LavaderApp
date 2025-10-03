# apps/notifications/forms/template.py
"""
Forms de apps.notifications

- TemplateForm: ABM de plantillas (únicas por empresa + validaciones simples).
- SendFromSaleForm: Enviar notificación desde una venta (elige plantilla activa,
  infiere canal/destinatario y valida según canal —email o E.164—).
- PreviewForm: Render de vista previa con/sin venta real.

Convenciones:
- Bootstrap 5: se inyectan clases en __init__ (form-control / form-select / etc.).
- Multi-tenant: los QuerySets se filtran por empresa en __init__.
"""

from __future__ import annotations

import re
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from ..models import PlantillaNotif, Canal

# Regex de apoyo (simple y suficiente para MVP)
EMAIL_RE = re.compile(r".+@.+\..+")
E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # ITU-T E.164, 7–15 dígitos


# ----------------------------
# Helpers Bootstrap + widgets
# ----------------------------
def _bootstrapify(form: forms.Form) -> None:
    """Inyecta clases Bootstrap 5 a todos los campos del form."""
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-select").strip()
        elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-check-input").strip()
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-control").strip()
            widget.attrs.setdefault("rows", 3)
        else:
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-control").strip()


def _validate_destinatario_por_canal(*, canal: str, destinatario: str) -> None:
    dest = (destinatario or "").strip()
    if not dest:
        raise ValidationError(
            "El destinatario no puede estar vacío.", code="empty")

    if canal == Canal.EMAIL:
        try:
            validate_email(dest)
        except ValidationError:
            raise ValidationError(
                "El email del destinatario no es válido.", code="invalid_email")
        if not EMAIL_RE.match(dest):
            raise ValidationError(
                "El email del destinatario no es válido (formato).", code="invalid_email_format")
    elif canal == Canal.WHATSAPP:
        if not E164_RE.match(dest):
            raise ValidationError(
                "El WhatsApp debe estar en formato E.164 (ej.: +549381XXXXXXX).", code="invalid_e164")
    else:
        raise ValidationError(
            "Canal no soportado en el MVP.", code="unsupported_channel")


# ----------------------------
# TemplateForm (ABM Plantillas)
# ----------------------------
class TemplateForm(forms.ModelForm):
    """
    ABM de PlantillaNotif.

    Reglas:
    - (empresa, clave) único → validación en clean() además del UniqueConstraint.
    - canal ∈ {email, whatsapp}.
    - Si canal=whatsapp → se oculta `asunto_tpl` en el form y se guarda vacío.
    - Si canal=email → `asunto_tpl` visible (no obligatorio en MVP).
    """

    class Meta:
        model = PlantillaNotif
        fields = ("clave", "canal", "asunto_tpl", "cuerpo_tpl", "activo")
        widgets = {
            "cuerpo_tpl": forms.Textarea(
                attrs={
                    "placeholder": "Ej.: Hola {{cliente.nombre}}, tu auto ({{vehiculo.patente}}) ya está listo para retirar..."}
            ),
            "asunto_tpl": forms.TextInput(
                attrs={
                    "placeholder": "Solo para email. Ej.: Tu auto está listo • {{empresa.nombre}}"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop("empresa", None)
        self.creado_por = kwargs.pop("creado_por", None)
        bound_data = kwargs.get("data")
        super().__init__(*args, **kwargs)

        if self.empresa is None:
            raise ValueError(
                "TemplateForm requiere 'empresa' para validar unicidad por tenant.")

        _bootstrapify(self)

        # Detectar canal (POST > instancia > initial)
        canal_actual = None
        if bound_data and "canal" in bound_data:
            canal_actual = bound_data.get("canal")
        elif getattr(self.instance, "pk", None):
            canal_actual = getattr(self.instance, "canal", None)
        else:
            canal_actual = self.initial.get("canal")

        # Si es WhatsApp → ocultamos/eliminamos asunto_tpl del form
        if canal_actual == Canal.WHATSAPP and "asunto_tpl" in self.fields:
            self.fields.pop("asunto_tpl")

    def clean_clave(self) -> str:
        clave = (self.cleaned_data.get("clave") or "").strip()
        if not clave:
            raise ValidationError("La clave es obligatoria.", code="required")

        qs = PlantillaNotif.objects.filter(
            empresa=self.empresa, clave__iexact=clave)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "Ya existe una plantilla con esa clave en esta empresa.", code="unique")
        return clave

    def clean(self):
        data = super().clean()
        canal = data.get("canal")

        if canal not in (Canal.EMAIL, Canal.WHATSAPP):
            raise ValidationError({"canal": "Canal no soportado en el MVP."})

        cuerpo = (data.get("cuerpo_tpl") or "").strip()
        if not cuerpo:
            raise ValidationError(
                {"cuerpo_tpl": "El cuerpo de la plantilla no puede estar vacío."})

        # WhatsApp: asunto vacío siempre
        if canal == Canal.WHATSAPP and "asunto_tpl" in data:
            data["asunto_tpl"] = ""
        return data

    def save(self, commit: bool = True):
        obj = super().save(commit=False)
        obj.empresa = self.empresa
        if obj.canal == Canal.WHATSAPP:
            obj.asunto_tpl = ""  # Forzar vacío en DB
        if self.creado_por and not obj.pk:
            obj.creado_por = self.creado_por
        if commit:
            obj.save()
        return obj


# ----------------------------
# SendFromSaleForm
# ----------------------------
class SendFromSaleForm(forms.Form):
    # (igual que antes, no tocamos nada)
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaNotif.objects.none(),
        label="Plantilla",
        help_text="Plantillas activas de esta empresa.",
    )
    destinatario = forms.CharField(
        label="Destinatario",
        max_length=255,
        help_text="Email (para canal email) o teléfono E.164 (para canal WhatsApp).",
    )
    nota_extra = forms.CharField(
        label="Nota adicional (opcional)",
        widget=forms.Textarea,
        required=False,
        help_text="Este texto se insertará en {{nota_extra}}.",
    )
    idempotency_key = forms.CharField(
        label="Idempotency key (opcional)",
        max_length=80,
        required=False,
        help_text="Se almacenará en el Log. En el MVP no evita duplicados.",
    )

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop("empresa", None)
        self.venta = kwargs.pop("venta", None)
        qs_plantillas = kwargs.pop("queryset_plantillas", None)
        initial_destinatario = kwargs.pop("initial_destinatario", None)
        super().__init__(*args, **kwargs)

        if self.empresa is None or self.venta is None:
            raise ValueError("SendFromSaleForm requiere 'empresa' y 'venta'.")

        if qs_plantillas is None:
            qs_plantillas = PlantillaNotif.objects.filter(
                empresa=self.empresa, activo=True)
        self.fields["plantilla"].queryset = qs_plantillas.order_by("clave")

        _bootstrapify(self)

        if initial_destinatario:
            self.fields["destinatario"].initial = initial_destinatario

    def clean_plantilla(self) -> PlantillaNotif:
        plantilla: PlantillaNotif = self.cleaned_data["plantilla"]
        if not plantilla.activo:
            raise ValidationError(
                "La plantilla seleccionada está inactiva.", code="inactive")
        if plantilla.empresa_id != self.empresa.id:
            raise ValidationError(
                "La plantilla no pertenece a la empresa activa.", code="tenant_mismatch")
        return plantilla

    def clean_destinatario(self) -> str:
        data = self.cleaned_data
        plantilla: PlantillaNotif | None = data.get(
            "plantilla") or self.fields["plantilla"].queryset.first()
        destinatario: str = (data.get("destinatario") or "").strip()

        if not plantilla:
            if not destinatario:
                raise ValidationError(
                    "El destinatario es obligatorio.", code="required")
            return destinatario

        _validate_destinatario_por_canal(
            canal=plantilla.canal, destinatario=destinatario)
        return destinatario

    def infer_destinatario_si_vacio(self) -> None:
        if self["destinatario"].value():
            return
        plantilla = None
        try:
            plantilla = self.fields["plantilla"].queryset.get(
                pk=self["plantilla"].value())
        except Exception:
            pass
        if not plantilla:
            return

        cliente = getattr(self.venta, "cliente", None)
        if plantilla.canal == Canal.EMAIL:
            val = getattr(cliente, "email", "") or ""
        elif plantilla.canal == Canal.WHATSAPP:
            val = getattr(cliente, "tel_wpp", "") or ""
        else:
            val = ""
        if val:
            self.fields["destinatario"].initial = val


# ----------------------------
# PreviewForm
# ----------------------------
class PreviewForm(forms.Form):
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaNotif.objects.none(),
        label="Plantilla",
    )
    venta_id = forms.CharField(
        required=False,
        label="Venta (opcional)",
        help_text="UUID de una venta real para vista previa con datos reales.",
    )
    nota_extra = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Nota adicional (opcional)",
    )

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop("empresa", None)
        qs_plantillas = kwargs.pop("queryset_plantillas", None)
        super().__init__(*args, **kwargs)

        if self.empresa is None:
            raise ValueError("PreviewForm requiere 'empresa'.")

        if qs_plantillas is None:
            qs_plantillas = PlantillaNotif.objects.filter(empresa=self.empresa)
        self.fields["plantilla"].queryset = qs_plantillas.order_by("clave")

        _bootstrapify(self)
