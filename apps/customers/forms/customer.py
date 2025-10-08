# apps/customers/forms/customer.py
from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from ..models import Cliente
from .. import normalizers


class CustomerForm(forms.ModelForm):
    """
    Formulario de alta/edición de Cliente.
    - Inyecta clases Bootstrap en widgets (form-control / form-select / form-check-input).
    - Normaliza email, documento, teléfono antes de guardar.
    - Convierte 'tags' desde un input de texto "coma-separado" a list[str] (JSONField).
    - Setea empresa y creado_por desde request (inyectado en get_form_kwargs).
    """

    class Meta:
        model = Cliente
        fields = [
            "tipo_persona",
            "nombre",
            "apellido",
            "razon_social",
            "documento",
            "email",
            "tel_wpp",
            "fecha_nac",
            "direccion",
            "localidad",
            "provincia",
            "cp",
            "tags",
            "notas",
            "activo",
        ]
        widgets = {
            "fecha_nac": forms.DateInput(attrs={"type": "date"}),
            "notas": forms.Textarea(attrs={"rows": 3}),
            # En UI se edita como texto separado por comas; se convierte en clean_tags()
            "tags": forms.TextInput(attrs={"placeholder": "Etiquetas separadas por comas (ej: vip, empresa)"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Si hay lista de tags en la instancia, mostrarla como texto comma-separated
        if "tags" in self.fields:
            current = self.initial.get("tags", None)
            if current is None and getattr(self.instance, "tags", None):
                current = self.instance.tags
            if isinstance(current, (list, tuple)):
                self.initial["tags"] = ", ".join(
                    [str(t) for t in current if str(t).strip()])

        # Inyectar clases Bootstrap cuidando el tipo de widget
        for name, field in self.fields.items():
            widget = field.widget
            input_type = getattr(widget, "input_type", "")
            if input_type in ("checkbox", "radio"):
                widget.attrs.setdefault("class", "form-check-input")
            elif widget.__class__.__name__ in ("Select", "SelectMultiple"):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    # ----------------- Normalizaciones de campos -----------------

    def clean_email(self):
        email = self.cleaned_data.get("email")
        return normalizers.clean_email(email)

    def clean_documento(self):
        doc = self.cleaned_data.get("documento")
        return normalizers.clean_documento(doc)

    def clean_tel_wpp(self):
        """
        Normaliza teléfonos de AR hacia formato E.164 (+549...):
        - Quita espacios, guiones y puntos.
        - Elimina '0' inicial (prefijo nacional) y '15' (móvil local).
        - Agrega +54; para WhatsApp suele requerirse +549 (móvil).
        - Delegamos validación final a normalizers.clean_tel_e164().
        """
        raw = (self.cleaned_data.get("tel_wpp") or "").strip()
        if not raw:
            return ""

        tel = raw.replace(" ", "").replace("-", "").replace(".", "")

        # Si ya viene con '+', delegamos al normalizer para validar
        if tel.startswith("+"):
            return normalizers.clean_tel_e164(tel)

        # Quitar '0' nacional y '15' móvil local comunes en AR
        if tel.startswith("0"):
            tel = tel[1:]
        if tel.startswith("15"):
            tel = tel[2:]

        # Asegurar prefijo país
        if not tel.startswith("54"):
            tel = "54" + tel

        # Heurística simple para móviles en WhatsApp: +549...
        # (Si ya trae 549, lo respetamos; si no, insertamos el '9' tras '54')
        if not tel.startswith("549"):
            tel = "549" + tel[2:]

        # Pasar a E.164 definitivo
        tel = "+" + tel
        return normalizers.clean_tel_e164(tel)

    def clean_tags(self):
        """
        Convierte el texto 'a, b, c' → ['a', 'b', 'c'] para guardarlo en JSONField.
        Si el usuario deja vacío, devuelve [].
        """
        value = self.cleaned_data.get("tags")
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            # Viene desde inicialización programática
            return [str(v).strip() for v in value if str(v).strip()]
        # Texto → lista
        parts = [p.strip() for p in str(value).split(",")]
        return [p for p in parts if p]

    # ----------------- Validaciones de duplicados por empresa -----------------

    def clean(self):
        """
        Chequea duplicados por empresa activa antes del guardado para
        devolver errores de campo en lugar de caer en 500 por constraints.
        """
        cleaned = super().clean()
        empresa = getattr(getattr(self, "request", None),
                          "empresa_activa", None)
        if not empresa:
            return cleaned  # En principio siempre hay tenancy; por las dudas.

        qs = Cliente.objects.filter(empresa=empresa)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        email = cleaned.get("email") or ""
        documento = cleaned.get("documento") or ""
        tel_wpp = cleaned.get("tel_wpp") or ""

        # Validamos solo si no están vacíos (igual que las UniqueConstraint condicionales).
        if email and qs.filter(email=email).exists():
            self.add_error(
                "email", "Ya existe un cliente con este email en la empresa.")
        if documento and qs.filter(documento=documento).exists():
            self.add_error(
                "documento", "Ya existe un cliente con este documento en la empresa.")
        if tel_wpp and qs.filter(tel_wpp=tel_wpp).exists():
            self.add_error(
                "tel_wpp", "Ya existe un cliente con este teléfono en la empresa.")

        return cleaned

    # ----------------- Guardado -----------------

    def save(self, commit=True):
        obj: Cliente = super().save(commit=False)

        # Normalizaciones de presentación
        obj.nombre = normalizers.capitalizar(obj.nombre)
        obj.apellido = normalizers.capitalizar(obj.apellido)
        obj.razon_social = normalizers.capitalizar(obj.razon_social)

        # Derivado para búsquedas laxas
        obj.tel_busqueda = normalizers.strip_tel(obj.tel_wpp)

        # Scope multi-tenant
        if self.request and hasattr(self.request, "empresa_activa") and not obj.empresa_id:
            obj.empresa = self.request.empresa_activa
        if self.request and hasattr(self.request, "user") and not obj.pk:
            obj.creado_por = self.request.user

        if commit:
            try:
                obj.full_clean()  # asegura validaciones del modelo (incluye constraints)
                obj.save()
            except ValidationError as ve:
                # Mapear errores del modelo al formulario y no guardar
                error_dict = getattr(ve, "message_dict", {}) or {}
                for field, msgs in error_dict.items():
                    if field == "__all__":
                        for m in msgs:
                            self.add_error(None, m)
                    else:
                        for m in msgs:
                            if field in self.fields:
                                self.add_error(field, m)
                            else:
                                self.add_error(None, f"{field}: {m}")
                return obj
            except IntegrityError as ie:
                # Condición de carrera contra UniqueConstraint: traducimos por nombre de constraint
                msg = str(ie)
                if "uniq_cliente_email_por_empresa" in msg:
                    self.add_error(
                        "email", "Ya existe un cliente con este email en la empresa.")
                elif "uniq_cliente_documento_por_empresa" in msg:
                    self.add_error(
                        "documento", "Ya existe un cliente con este documento en la empresa.")
                elif "uniq_cliente_tel_por_empresa" in msg:
                    self.add_error(
                        "tel_wpp", "Ya existe un cliente con este teléfono en la empresa.")
                else:
                    self.add_error(
                        None, "No se pudo guardar por una restricción de unicidad.")
                return obj
            # ModelForm ya guarda M2M si existieran (no hay en este form). No hace falta save_m2m.
        return obj
