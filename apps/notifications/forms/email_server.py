from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import EmailServer


class EmailServerForm(forms.ModelForm):
    new_password = forms.CharField(
        label=_("Contraseña"),
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_("Dejar vacío para mantener la contraseña actual."),
    )

    class Meta:
        model = EmailServer
        fields = [
            "nombre",
            "host",
            "port",
            "use_tls",
            "use_ssl",
            "username",
            "new_password",
            "remitente_por_defecto",
            "activo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inyectamos clase Bootstrap
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
        self.fields["use_tls"].widget.attrs.update(
            {"class": "form-check-input"})
        self.fields["use_ssl"].widget.attrs.update(
            {"class": "form-check-input"})
        self.fields["activo"].widget.attrs.update(
            {"class": "form-check-input"})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_tls") and cleaned.get("use_ssl"):
            raise forms.ValidationError(
                _("No podés activar TLS y SSL al mismo tiempo."))
        return cleaned

    def save(self, commit=True):
        obj: EmailServer = super().save(commit=False)
        pwd = self.cleaned_data.get("new_password")
        if pwd:
            obj.set_password(pwd)
        if commit:
            obj.save()
        return obj
