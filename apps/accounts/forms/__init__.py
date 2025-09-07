from allauth.account.forms import LoginForm as AllauthLoginForm, SignupForm as AllauthSignupForm
from django import forms
from django.forms import widgets

from allauth.account.forms import (
    ResetPasswordForm as AllauthResetPasswordForm,
    ResetPasswordKeyForm as AllauthResetPasswordKeyForm,
    ChangePasswordForm as AllauthChangePasswordForm,
)

# --- Helpers Bootstrap --------------------------------------------------------
INPUT_CLASSES = "form-control"
SELECT_CLASSES = "form-select"
CHECKBOX_CLASSES = "form-check-input"


def _add_bootstrap_classes(bound_form: forms.BaseForm) -> None:
    """
    Aplica clases Bootstrap 5 a todos los campos:
    - Inputs/textarea: form-control
    - Selects: form-select
    - Checkboxes: form-check-input
    Además, si el form está ligado (is_bound) y el campo tiene errores,
    agrega la clase 'is-invalid' para que Bootstrap muestre el estado de error.
    """
    for name, field in bound_form.fields.items():
        w = field.widget
        # Elegir clase base por tipo de widget
        if isinstance(w, (widgets.CheckboxInput,)):
            base_class = CHECKBOX_CLASSES
        elif isinstance(w, (widgets.Select, widgets.SelectMultiple)):
            base_class = SELECT_CLASSES
        else:
            base_class = INPUT_CLASSES

        # Merge de clases existentes
        classes = (w.attrs.get("class", "") + " " + base_class).strip()
        w.attrs["class"] = classes

        # Errores -> is-invalid (sólo si está ligado)
        if bound_form.is_bound and name in bound_form.errors:
            w.attrs["class"] += " is-invalid"

# --- Formularios de Allauth con Bootstrap ------------------------------------


class LoginForm(AllauthLoginForm):
    """
    Login con clases Bootstrap y atributos útiles de accesibilidad/UX.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Placeholders y autocomplete correctos
        if "login" in self.fields:
            # allauth usa 'login' (username o email según config)
            self.fields["login"].widget.attrs.update({
                "placeholder": "Usuario o Email",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            })
        if "password" in self.fields:
            self.fields["password"].widget.attrs.update({
                "placeholder": "Contraseña",
                "autocomplete": "current-password",
            })
        if "remember" in self.fields:
            # checkbox
            self.fields["remember"].widget.attrs.update({})

        # Aplicar Bootstrap
        _add_bootstrap_classes(self)


class SignupForm(AllauthSignupForm):
    """
    Signup con campos extra (first_name/last_name) y clases Bootstrap.
    """
    first_name = forms.CharField(
        label="Nombre", max_length=150, required=False)
    last_name = forms.CharField(
        label="Apellido", max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Atributos UX/semánticos
        # Si tu settings es email-only, allauth no usa username; este bloque es seguro.
        if "username" in self.fields:
            self.fields["username"].widget.attrs.update({
                "placeholder": "Usuario",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            })
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({
                "placeholder": "Email",
                "autocomplete": "email",
            })
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.update({
                "placeholder": "Contraseña",
                "autocomplete": "new-password",
            })
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update({
                "placeholder": "Repetir contraseña",
                "autocomplete": "new-password",
            })

        for name in ("first_name", "last_name"):
            if name in self.fields:
                self.fields[name].widget.attrs.update({
                    "placeholder": self.fields[name].label,
                })

        _add_bootstrap_classes(self)

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data.get(
            "first_name", "") or user.first_name
        user.last_name = self.cleaned_data.get(
            "last_name", "") or user.last_name
        user.save(update_fields=["first_name", "last_name"])
        return user


class ResetPasswordForm(AllauthResetPasswordForm):
    """Solicitar reset por email (añade clases Bootstrap)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Placeholders/semántica
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({
                "placeholder": "Email",
                "autocomplete": "email",
            })
        _add_bootstrap_classes(self)


class ResetPasswordKeyForm(AllauthResetPasswordKeyForm):
    """Ingresar nueva contraseña desde el link del email (añade clases Bootstrap)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            if name in self.fields:
                self.fields[name].widget.attrs.update({
                    "placeholder": self.fields[name].label,
                    "autocomplete": "new-password",
                })
        _add_bootstrap_classes(self)


class ChangePasswordForm(AllauthChangePasswordForm):
    """(Opcional) Cambiar contraseña estando logueado, con Bootstrap."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mapping = {
            "oldpassword": {"autocomplete": "current-password"},
            "password1": {"autocomplete": "new-password"},
            "password2": {"autocomplete": "new-password"},
        }
        for name, attrs in mapping.items():
            if name in self.fields:
                self.fields[name].widget.attrs.update(attrs)
        _add_bootstrap_classes(self)
