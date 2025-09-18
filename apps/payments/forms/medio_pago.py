# apps/payments/forms/medio_pago.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.payments.models import MedioPago


class MedioPagoForm(forms.ModelForm):
    class Meta:
        model = MedioPago
        fields = ["nombre", "activo"]

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop("empresa", None)
        super().__init__(*args, **kwargs)
        self.fields["nombre"].widget.attrs.update({
            "class": "form-control",
            "placeholder": _("Ej: Efectivo, MercadoPago, Transferencia BBVA"),
        })
        self.fields["activo"].widget.attrs.update(
            {"class": "form-check-input"})

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise ValidationError(_("Ingresá un nombre."))
        if self.empresa:
            qs = MedioPago.objects.filter(
                empresa=self.empresa, nombre__iexact=nombre)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    _("Ya existe un medio de pago con ese nombre en esta empresa."))
        return nombre

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.empresa is not None:
            obj.empresa = self.empresa
        if commit:
            obj.full_clean()
            obj.save()
        return obj
