# apps/org/forms/org.py

from django import forms
from ..models import Empresa, Sucursal
from django.contrib.auth import get_user_model
from apps.accounts.models import EmpresaMembership


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nombre", "subdominio", "logo", "activo"]

        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre de la empresa"}),
            "subdominio": forms.TextInput(attrs={"class": "form-control", "placeholder": "subdominio"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ["nombre", "direccion"]

        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre de la sucursal"}),
            "direccion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Dirección"}),
        }


class EmpleadoForm(forms.Form):
    email = forms.EmailField(label="Email")
    rol = forms.ChoiceField(choices=EmpresaMembership.ROLE_CHOICES)
    sucursal_asignada = forms.ModelChoiceField(
        queryset=Sucursal.objects.none(),
        required=False,
        label="Sucursal asignada"
    )
    password_inicial = forms.CharField(
        label="Contraseña inicial",
        widget=forms.PasswordInput,
        required=True
    )

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop("empresa", None)
        super().__init__(*args, **kwargs)
        if empresa:
            self.fields["sucursal_asignada"].queryset = empresa.sucursales.all()
