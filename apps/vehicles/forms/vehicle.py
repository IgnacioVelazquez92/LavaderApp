"""
vehicle.py — Formularios del módulo Vehicles

Incluye:
- VehicleForm: Alta/Edición de Vehiculo con validaciones de:
  - formato y unicidad de patente dentro de la empresa activa,
  - año razonable,
  - pertenencia del cliente a la empresa activa.
- VehicleFilterForm: filtros básicos para listados (cliente + búsqueda por patente/marca/modelo).
- TipoVehiculoForm: Alta/Edición de TipoVehiculo (slug único por empresa).
"""

from datetime import date
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.customers.models import Cliente
from ..models import Vehiculo, TipoVehiculo
from ..validators import (
    normalizar_patente,
    validate_patente_format,
    ensure_patente_unique_in_company,
)


# ----------------------------
# Helpers de estilo (opcional)
# ----------------------------
def _add_bootstrap_classes(form: forms.Form) -> None:
    """
    Inyecta clases Bootstrap 5 a los widgets.
    Si preferís manejar clases en los templates, podés eliminar esta función.
    """
    for name, field in form.fields.items():
        widget = field.widget
        # Checkboxes y radios
        if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-check-input").strip()
        # Selects
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-select").strip()
        # Inputs/textarea por defecto
        else:
            widget.attrs["class"] = (widget.attrs.get(
                "class", "") + " form-control").strip()
        # Placeholders mínimos
        if not widget.attrs.get("placeholder"):
            widget.attrs["placeholder"] = field.label or name.capitalize()


# ----------------------------
# VehicleForm (Create/Update)
# ----------------------------
class VehicleForm(forms.ModelForm):
    """
    Formulario de Alta/Edición de Vehiculo.

    Cómo usar en CBVs (ejemplo):
    -----------------------------
    class VehicleCreateView(CreateView):
        model = Vehiculo
        form_class = VehicleForm
        template_name = "vehicles/form.html"
        success_url = reverse_lazy("vehicles:list")

        def get_form_kwargs(self):
            kwargs = super().get_form_kwargs()
            kwargs["empresa"] = getattr(self.request, "empresa_activa", None)
            # opcional, para filtrar clientes por sucursal si aplica
            # kwargs["sucursal"] = getattr(self.request, "sucursal_activa", None)
            return kwargs

        def form_valid(self, form):
            self.object = form.save()  # el form setea empresa y normaliza patente
            messages.success(self.request, "Vehículo creado con éxito.")
            return redirect(self.get_success_url())

    Notas:
    - Este form exige recibir 'empresa' en __init__ para validar unicidad y filtrar querysets.
    - La patente se normaliza y valida formato antes de guardar.
    """

    # Campos adicionales de UX (si quisieras, opcionales)
    patente = forms.CharField(
        label=_("Patente"),
        help_text=_("Ej.: ABC123 o AB123CD (guiones/espacios se ignoran)."),
        max_length=10,
    )

    # Rango razonable de años (editable si tu negocio lo requiere)
    ANIO_MIN = 1950
    ANIO_MAX = date.today().year + 1

    def __init__(self, *args, empresa=None, sucursal=None, apply_bootstrap: bool = True, **kwargs):
        """
        Args:
            empresa: Empresa activa (OBLIGATORIO para validar unicidad).
            sucursal: opcional, por si en el futuro querés filtrar clientes por sucursal.
            apply_bootstrap: si True, se inyectan clases Bootstrap a los widgets.
        """
        super().__init__(*args, **kwargs)
        if empresa is None:
            raise ValueError(
                "VehicleForm requiere 'empresa' para validar y asignar tenant.")

        self.empresa = empresa
        self.sucursal = sucursal

        # Filtrar clientes a la empresa activa (y activos)
        self.fields["cliente"].queryset = Cliente.objects.filter(
            empresa=self.empresa, activo=True)

        # Filtrar tipos de vehículo propios de la empresa (activos)
        self.fields["tipo"].queryset = TipoVehiculo.objects.filter(
            empresa=self.empresa, activo=True)

        # Inyectar Bootstrap (opcional)
        if apply_bootstrap:
            _add_bootstrap_classes(self)

        # Hints/labels
        self.fields["anio"].help_text = _(
            f"Ingrese un año entre {self.ANIO_MIN} y {self.ANIO_MAX} (opcional).")

    class Meta:
        model = Vehiculo
        fields = [
            "cliente",
            "tipo",
            "marca",
            "modelo",
            "anio",
            "color",
            "patente",
            "notas",
            "activo",
        ]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "cliente": _("Propietario del vehículo (de la empresa activa)."),
            "tipo": _("Clasificación (auto, moto, utilitario, etc.)."),
        }

    # --- Validaciones de campo ---
    def clean_patente(self) -> str:
        raw = self.cleaned_data.get("patente", "")
        # 1) formato
        validate_patente_format(raw)
        # 2) normalizar
        norm = normalizar_patente(raw)
        return norm

    def clean_anio(self) -> Optional[int]:
        anio = self.cleaned_data.get("anio")
        if anio is None:
            return anio
        if not (self.ANIO_MIN <= anio <= self.ANIO_MAX):
            raise ValidationError(
                _(f"El año debe estar entre {self.ANIO_MIN} y {self.ANIO_MAX}.")
            )
        return anio

    # --- Validaciones de formulario ---
    def clean(self):
        cleaned = super().clean()

        # El cliente debe pertenecer a la empresa activa (defensa extra, por si manipulan el form)
        cliente = cleaned.get("cliente")
        if cliente and cliente.empresa_id != self.empresa.id:
            self.add_error("cliente", _(
                "El cliente seleccionado no pertenece a tu empresa."))

        # Unicidad de patente por empresa (considerando soft delete activo=True)
        patente = cleaned.get("patente")
        if patente:
            try:
                ensure_patente_unique_in_company(
                    empresa=self.empresa,
                    patente=patente,
                    exclude_pk=self.instance.pk if self.instance and self.instance.pk else None,
                    only_active=True,
                )
            except ValidationError as e:
                self.add_error("patente", e)

        return cleaned

    # --- Guardado ---
    def save(self, commit: bool = True) -> Vehiculo:
        """
        Setea empresa y garantiza patente normalizada antes de persistir.
        """
        obj: Vehiculo = super().save(commit=False)
        obj.empresa = self.empresa
        obj.patente = normalizar_patente(
            self.cleaned_data.get("patente", obj.patente))
        if commit:
            obj.save()
        return obj


# ----------------------------
# VehicleFilterForm (listado)
# ----------------------------
class VehicleFilterForm(forms.Form):
    """
    Filtros para el listado de vehículos.
    Pensado para GET (?q=...&cliente=...&solo_activos=1)

    Uso típico en ListView.get_queryset():
        form = VehicleFilterForm(self.request.GET, empresa=self.request.empresa_activa)
        if form.is_valid():
            qs = selectors.buscar_vehiculos(
                empresa=self.request.empresa_activa,
                q=form.cleaned_data["q"],
                cliente=form.cleaned_data["cliente"],
                solo_activos=form.cleaned_data["solo_activos"],
            )
    """
    q = forms.CharField(
        label=_("Buscar"),
        required=False,
        help_text=_("Patente, marca o modelo."),
    )
    cliente = forms.ModelChoiceField(
        label=_("Cliente"),
        required=False,
        queryset=Cliente.objects.none(),  # se setea en __init__
    )
    solo_activos = forms.BooleanField(
        label=_("Solo activos"),
        required=False,
        initial=True,
    )

    def __init__(self, *args, empresa=None, apply_bootstrap: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is None:
            raise ValueError(
                "VehicleFilterForm requiere 'empresa' para filtrar opciones.")
        self.empresa = empresa
        self.fields["cliente"].queryset = Cliente.objects.filter(
            empresa=self.empresa, activo=True)
        if apply_bootstrap:
            _add_bootstrap_classes(self)

    def cleaned_query(self) -> str:
        """
        Devuelve la query normalizada (para patente también elimina guiones/espacios).
        """
        q = (self.cleaned_data.get("q") or "").strip()
        if not q:
            return ""
        # Permitimos buscar por patente en cualquier formato
        return normalizar_patente(q)


# ----------------------------
# TipoVehiculoForm
# ----------------------------
class TipoVehiculoForm(forms.ModelForm):
    """
    Form de alta/edición de TipoVehiculo. El slug debe ser único por empresa.
    """

    def __init__(self, *args, empresa=None, apply_bootstrap: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is None:
            raise ValueError("TipoVehiculoForm requiere 'empresa'.")
        self.empresa = empresa
        if apply_bootstrap:
            _add_bootstrap_classes(self)

    class Meta:
        model = TipoVehiculo
        fields = ["nombre", "slug", "activo"]

    def clean_slug(self) -> str:
        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            raise ValidationError(_("El slug es obligatorio."))
        # Unicidad (empresa, slug)
        qs = TipoVehiculo.objects.filter(empresa=self.empresa, slug=slug)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                _("Ya existe un tipo de vehículo con este slug en tu empresa."))
        return slug

    def save(self, commit: bool = True) -> TipoVehiculo:
        obj: TipoVehiculo = super().save(commit=False)
        obj.empresa = self.empresa
        if commit:
            obj.save()
        return obj
