# apps/catalog/forms/service.py
from __future__ import annotations

from typing import Optional

from django import forms
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower

from apps.catalog.models import Servicio


class ServiceForm(forms.ModelForm):
    """
    Formulario de alta/edición de Servicio.

    - Multi-tenant: requiere `request` en __init__ para tomar `request.empresa_activa`.
    - Unicidad:
        * `nombre` único por empresa (case-insensitive).
        * `slug` único por empresa (si el usuario lo especifica manualmente).
    - UX/Reglas:
        * En creación, `activo` se fuerza a True (aunque no se muestre).
        * En edición, `activo` es editable.
    - Normalizaciones mínimas: strip de espacios en `nombre` y `descripcion`.
    """

    # Nota: el template aplica clases Bootstrap; aquí no inyectamos CSS.
    class Meta:
        model = Servicio
        fields = ["nombre", "descripcion", "slug", "activo"]
        widgets = {
            # En el MVP solemos ocultar el slug; si lo querés visible, cambiá a TextInput.
            "slug": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos request para acceder a empresa activa (inyectado por TenancyMiddleware).
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Empresa activa (tenant) requerida para validar y guardar
        self.empresa_activa = getattr(
            self.request, "empresa_activa", None) if self.request else None

        # Reglas de edición/creación para el campo "activo"
        if self.instance and self.instance.pk:
            self.fields["activo"].disabled = False
        else:
            self.fields["activo"].initial = True
            # evitamos que llegue un False inesperado
            self.fields["activo"].disabled = True

        # ---------- Bootstrap classes ----------
        # Inputs de texto/textarea
        text_like = ("nombre", "descripcion")
        for name in text_like:
            if name in self.fields:
                widget = self.fields[name].widget
                base = widget.attrs.get("class", "").strip()
                widget.attrs["class"] = (
                    " ".join([base, "form-control"]).strip()).strip()
        # Textarea rows
        if "descripcion" in self.fields:
            self.fields["descripcion"].widget.attrs.setdefault("rows", "3")

        # Checkbox/switch
        if "activo" in self.fields:
            w = self.fields["activo"].widget
            base = w.attrs.get("class", "").strip()
            w.attrs["class"] = (
                " ".join([base, "form-check-input"]).strip()).strip()

        # En forms ligados, marcar errores con is-invalid
        if self.is_bound:
            for name, field in self.fields.items():
                if self.errors.get(name):
                    base = field.widget.attrs.get("class", "").strip()
                    field.widget.attrs["class"] = (
                        base + " is-invalid").strip()

    # -----------------------
    # Limpiezas y validaciones
    # -----------------------
    def clean_nombre(self) -> str:
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise ValidationError("El nombre es obligatorio.")
        # Unicidad case-insensitive por empresa
        if self._nombre_duplicado(nombre):
            raise ValidationError(
                "Ya existe un servicio con ese nombre en esta empresa.")
        return nombre

    def clean_descripcion(self) -> str:
        descripcion = (self.cleaned_data.get("descripcion") or "").strip()
        return descripcion

    def clean_slug(self) -> str:
        """
        El modelo genera slug automáticamente si viene vacío.
        Si el usuario lo especifica, aseguramos unicidad por empresa.
        """
        slug = (self.cleaned_data.get("slug") or "").strip()
        if slug and self._slug_duplicado(slug):
            raise ValidationError("El slug ya está en uso en esta empresa.")
        return slug

    def clean(self):
        """
        Validaciones de formulario que requieren múltiples campos o contexto.
        """
        cleaned = super().clean()

        # Verificar empresa activa presente
        if not self.empresa_activa:
            # Esto indica un uso incorrecto del form (falta middleware o pasar request).
            raise ValidationError(
                "No se encontró una empresa activa en el contexto. "
                "Asegúrate de utilizar TenancyMiddleware y de pasar `request` al formulario."
            )

        return cleaned

    # -----------------------
    # Persistencia
    # -----------------------
    def save(self, commit: bool = True) -> Servicio:
        """
        - Asigna la empresa activa antes de guardar.
        - Fuerza `activo=True` en creación (cuando el campo está disabled).
        - El modelo se encarga de generar `slug` si está vacío.
        """
        instance: Servicio = super().save(commit=False)

        # Scoping multi-tenant
        instance.empresa = self.empresa_activa

        # Normalizaciones defensivas
        if instance.nombre:
            instance.nombre = " ".join(instance.nombre.split())
        if instance.descripcion:
            instance.descripcion = instance.descripcion.strip()

        # En creación, garantizamos activo=True
        if not instance.pk:
            instance.activo = True

        if commit:
            instance.save()

        return instance

    # -----------------------
    # Helpers internos
    # -----------------------
    def _nombre_duplicado(self, nombre: str) -> bool:
        if not self.empresa_activa:
            return False
        qs = (
            Servicio.objects.filter(empresa=self.empresa_activa)
            .annotate(nombre_ci=Lower("nombre"))
            .filter(nombre_ci=nombre.lower())
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.exists()

    def _slug_duplicado(self, slug: str) -> bool:
        if not self.empresa_activa or not slug:
            return False
        qs = Servicio.objects.filter(empresa=self.empresa_activa, slug=slug)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.exists()
