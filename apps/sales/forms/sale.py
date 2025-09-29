# apps/sales/forms/sale.py
from django import forms
from apps.sales.models import Venta
from apps.customers.models import Cliente
from apps.vehicles.models import Vehiculo


class VentaForm(forms.ModelForm):
    """
    Crear/editar venta:
    - Sucursal NO se elige: la toma la vista desde request.sucursal_activa.
    - Vehículo filtrado por cliente seleccionado.
    - Validación: vehiculo.cliente == cliente y misma empresa.
    """
    class Meta:
        model = Venta
        fields = ["cliente", "vehiculo", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 3}),  # altura razonable
        }

    def __init__(self, *args, empresa=None, cliente_id=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Querysets filtrados por empresa
        if empresa is None:
            self.fields["cliente"].queryset = Cliente.objects.none()
            self.fields["vehiculo"].queryset = Vehiculo.objects.none()
        else:
            self.fields["cliente"].queryset = (
                Cliente.objects.filter(empresa=empresa, activo=True)
                .order_by("nombre", "apellido")
            )
            if cliente_id:
                self.fields["vehiculo"].queryset = (
                    Vehiculo.objects.filter(
                        empresa=empresa, cliente_id=cliente_id, activo=True
                    ).order_by("patente")
                )
            else:
                self.fields["vehiculo"].queryset = Vehiculo.objects.none()
                # Deshabilitar select de vehículo hasta elegir cliente (solo UX)
                self.fields["vehiculo"].widget.attrs["disabled"] = "disabled"

        # ===== Bootstrap classes =====
        self.fields["cliente"].widget.attrs.setdefault("class", "form-select")
        self.fields["vehiculo"].widget.attrs.setdefault("class", "form-select")
        self.fields["notas"].widget.attrs.setdefault("class", "form-control")
        self.fields["notas"].widget.attrs.setdefault(
            "placeholder", "Observaciones (opcional)")

        # is-invalid cuando hay errores
        if self.is_bound:
            for name, field in self.fields.items():
                if self.errors.get(name):
                    css = field.widget.attrs.get("class", "")
                    field.widget.attrs["class"] = f"{css} is-invalid".strip()

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")
        vehiculo = cleaned.get("vehiculo")

        # Si venía deshabilitado por GET, quitar flag para no romper POST
        if "disabled" in self.fields["vehiculo"].widget.attrs:
            self.fields["vehiculo"].widget.attrs.pop("disabled", None)

        if not cliente or not vehiculo:
            return cleaned

        # El vehículo debe pertenecer al cliente
        if vehiculo.cliente_id != cliente.id:
            self.add_error(
                "vehiculo", "El vehículo seleccionado no pertenece al cliente elegido.")

        # Misma empresa por seguridad
        if getattr(cliente, "empresa_id", None) != getattr(vehiculo, "empresa_id", None):
            self.add_error(
                "vehiculo", "Vehículo y cliente no pertenecen a la misma empresa.")

        return cleaned
