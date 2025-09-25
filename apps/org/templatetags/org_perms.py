# apps/org/templatetags/org_perms.py
from django import template
from apps.org.permissions import has_empresa_perm, Perm
from apps.org.models import Empresa

register = template.Library()


@register.simple_tag(takes_context=True)
def can(context, perm_code: str):
    """
    Uso:
      {% load org_perms %}
      {% can "org.sucursales.manage" as puede %}
      {% if puede %} ... {% endif %}
    """
    request = context.get("request")
    if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
        return False

    emp = None
    emp_id = request.session.get("empresa_id")
    if emp_id:
        emp = Empresa.objects.filter(pk=emp_id, activo=True).first()
    if not emp:
        return False

    try:
        perm = Perm(perm_code)
    except ValueError:
        # si el código no existe en Perm, devolvemos False
        return False

    return has_empresa_perm(request.user, emp, perm)
