# apps/saas/forms/__init__.py
"""
Formularios del módulo SaaS.

Convención:
- Usamos Bootstrap 5 aplicando clases desde el form (mixin) para inputs/selects/checkboxes.
- No añadimos lógica de negocio aquí; solo validación de campos del propio modelo.
"""

from .plan import PlanForm
from .subscription import SubscriptionForm

__all__ = ["PlanForm", "SubscriptionForm"]
