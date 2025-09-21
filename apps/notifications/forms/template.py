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
- Reglas de negocio: SOLO se permitirá el envío si la venta está "terminado"
  (validado en la vista/service; aquí validamos formato/destinatario/plantilla activa).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

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
        # Selects
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            cls = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{cls} form-select".strip()
        # Checkboxes / radios
        elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
            cls = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{cls} form-check-input".strip()
        # Textareas
        elif isinstance(widget, forms.Textarea):
            cls = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{cls} form-control".strip()
            widget.attrs.setdefault("rows", 3)
        # Inputs de texto/números
        else:
            cls = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{cls} form-control".strip()


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
# TemplateForm
# ----------------------------
class TemplateForm(forms.ModelForm):
    """
    ABM de PlantillaNotif.

    Reglas:
    - (empresa, clave) único → validación en clean() además del UniqueConstraint.
    - canal ∈ {email, whatsapp}.
    - asunto_tpl solo es requerido si el canal es email y el usuario lo completa (no obligatorio).
    """

    class Meta:
        model = PlantillaNotif
        fields = ("clave", "canal", "asunto_tpl", "cuerpo_tpl", "activo")
        widgets = {
            "cuerpo_tpl": forms.Textarea(attrs={"placeholder": "Ej.: Hola {{cliente.nombre}}, tu auto ({{vehiculo.patente}}) ya está listo para retirar..."}),
            "asunto_tpl": forms.TextInput(attrs={"placeholder": "Solo para email. Ej.: Tu auto está listo • {{empresa.nombre}}"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Se espera que la vista le pase:
        - empresa: instancia de org.Empresa (obligatoria para ABM multi-tenant).
        - creado_por: user opcional (solo para setear en save()).
        """
        self.empresa = kwargs.pop("empresa", None)
        self.creado_por = kwargs.pop("creado_por", None)
        super().__init__(*args, **kwargs)
        if self.empresa is None:
            raise ValueError(
                "TemplateForm requiere 'empresa' para validar unicidad por tenant.")

        _bootstrapify(self)

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
        # Nada especial: asunto_tpl es opcional incluso en email.
        if canal not in (Canal.EMAIL, Canal.WHATSAPP):
            raise ValidationError({"canal": "Canal no soportado en el MVP."})
        # cuerpo_tpl no vacío (hay CheckConstraint, pero reforzamos en form)
        cuerpo = (data.get("cuerpo_tpl") or "").strip()
        if not cuerpo:
            raise ValidationError(
                {"cuerpo_tpl": "El cuerpo de la plantilla no puede estar vacío."})
        return data

    def save(self, commit: bool = True):
        obj = super().save(commit=False)
        obj.empresa = self.empresa
        if self.creado_por and not obj.pk:
            obj.creado_por = self.creado_por
        if commit:
            obj.save()
        return obj


# ----------------------------
# SendFromSaleForm
# ----------------------------
class SendFromSaleForm(forms.Form):
    """
    Form para enviar notificación desde una Venta.

    Campos:
    - plantilla (ModelChoice) → filtrada a plantillas ACTIVAS de la empresa.
    - destinatario (email o E.164) → prellenado desde Cliente según canal de la plantilla.
    - nota_extra (textarea) → opcional; se inyecta como {{nota_extra}}.
    - idempotency_key (opcional) → guardada en Log; sin deduplicar en MVP.

    Uso:
        form = SendFromSaleForm(
            empresa=request.empresa_activa,
            venta=venta,
            queryset_plantillas=PlantillaNotif.objects.filter(empresa=request.empresa_activa, activo=True),
            initial_destinatario="+549381..." or "mail@dominio.com"
        )

    La vista debe:
    - pasar 'empresa' y 'venta'.
    - pasar 'queryset_plantillas' (ya filtrado por empresa y activo).
    - opcionalmente setear 'initial_destinatario'; si no, el form intentará inferirlo
      a partir de la plantilla elegida y los datos del cliente.
    """

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

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        self.empresa = kwargs.pop("empresa", None)
        self.venta = kwargs.pop("venta", None)
        qs_plantillas = kwargs.pop("queryset_plantillas", None)
        initial_destinatario = kwargs.pop("initial_destinatario", None)

        super().__init__(*args, **kwargs)

        if self.empresa is None or self.venta is None:
            raise ValueError("SendFromSaleForm requiere 'empresa' y 'venta'.")

        # Filtrado de plantillas activas por empresa
        if qs_plantillas is None:
            qs_plantillas = PlantillaNotif.objects.filter(
                empresa=self.empresa, activo=True)
        self.fields["plantilla"].queryset = qs_plantillas.order_by("clave")

        # Bootstrap
        _bootstrapify(self)

        # Sugerir destinatario si vino inicial
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
        # Validamos el formato según el canal de la plantilla elegida
        data = self.cleaned_data
        plantilla: PlantillaNotif | None = data.get(
            "plantilla") or self.fields["plantilla"].queryset.first()
        destinatario: str = (data.get("destinatario") or "").strip()

        if not plantilla:
            # Si no hay plantilla aún (POST inválido), validación mínima
            if not destinatario:
                raise ValidationError(
                    "El destinatario es obligatorio.", code="required")
            return destinatario

        _validate_destinatario_por_canal(
            canal=plantilla.canal, destinatario=destinatario)
        return destinatario

    # Ayuda para la vista: inferir destinatario por canal si el campo quedó vacío.
    def infer_destinatario_si_vacio(self) -> None:
        """
        Si el usuario no tipeó destinatario, completamos según canal y datos del cliente.
        Llamar en la vista antes de is_valid() si se quiere autocompletar.
        """
        if self["destinatario"].value():
            return  # ya hay algo cargado

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
    """
    Form simple para vista previa de una plantilla.
    - plantilla: se filtra por empresa (activas e inactivas; es preview).
    - venta_id (opcional): la vista puede pasar la venta real; si no, se usa contexto simulado.
    - nota_extra: texto opcional para {{nota_extra}}.

    La lógica de render vive en services/renderers.py; aquí solo recolectamos parámetros.
    """

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
