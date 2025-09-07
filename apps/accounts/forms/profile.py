from django import forms
from django.contrib.auth import get_user_model
from django.forms import widgets

User = get_user_model()

INPUT_CLASSES = "form-control"
SELECT_CLASSES = "form-select"
CHECKBOX_CLASSES = "form-check-input"


def _add_bootstrap_classes(bound_form: forms.BaseForm) -> None:
    for name, field in bound_form.fields.items():
        w = field.widget
        if isinstance(w, (widgets.CheckboxInput,)):
            base_class = CHECKBOX_CLASSES
        elif isinstance(w, (widgets.Select, widgets.SelectMultiple)):
            base_class = SELECT_CLASSES
        else:
            base_class = INPUT_CLASSES
        classes = (w.attrs.get("class", "") + " " + base_class).strip()
        w.attrs["class"] = classes
        if bound_form.is_bound and name in bound_form.errors:
            w.attrs["class"] += " is-invalid"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Placeholders útiles
        if "first_name" in self.fields:
            self.fields["first_name"].widget.attrs.update(
                {"placeholder": "Nombre"})
        if "last_name" in self.fields:
            self.fields["last_name"].widget.attrs.update(
                {"placeholder": "Apellido"})
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({
                "placeholder": "Email",
                "autocomplete": "email",
            })
        _add_bootstrap_classes(self)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user
