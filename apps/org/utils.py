from apps.org.models import Empresa, CashboxPolicy


def get_cashbox_policy(empresa: Empresa) -> str:
    return getattr(empresa, "cashbox_policy", CashboxPolicy.PAYMENTS_ONLY)
