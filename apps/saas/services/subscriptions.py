# apps/saas/services/subscriptions.py
"""
Servicios de Suscripciones SaaS.

Cubre:
- Asignar plan por defecto al crear empresa (start trial si corresponde).
- Crear/cambiar suscripción (cambio de plan).
- Renovaciones y gestión de estados de pago (stubs para pasarela).
- Recalcular estado (activa/vencida/suspendida) según fechas.

Integraciones futuras:
- Webhooks de Mercado Pago/Stripe: confirmar pago y llamar a `mark_paid_cycle`.
- Cron/management command para recomputar estados en lote (opcional).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.org.models import Empresa
from ..models import SuscripcionSaaS, PlanSaaS
from ..selectors import plan_default, suscripcion_de
from . import ServiceError, ServiceResult

logger = logging.getLogger(__name__)


# ---------------------------
# Alta automática con plan default
# ---------------------------

@transaction.atomic
def ensure_default_subscription_for_empresa(*, empresa: Empresa) -> ServiceResult:
    """
    Si la empresa no tiene suscripción, crea una con el plan default activo.
    - Si el plan tiene trial_days>0: inicializa trial (payment_status='trial').
    - Estado funcional por defecto: 'activa'.
    - inicio = hoy; fin = None (la vigencia funcional se controla con estado/fechas;
      el trial se muestra por UI usando trial_ends_at).

    Retorna:
        ServiceResult(ok=True, data={"suscripcion": sub}) si se crea,
        ServiceResult(ok=True, message="ya-existia", data={"suscripcion": sub}) si ya tenía.
    """
    sub = suscripcion_de(empresa)
    if sub:
        return ServiceResult(ok=True, message="ya-existia", data={"suscripcion": sub})

    plan = plan_default()
    if not plan:
        raise ServiceError(
            "No hay plan por defecto activo para asignar a la nueva empresa.")

    sub = SuscripcionSaaS.objects.create(
        empresa=empresa,
        plan=plan,
        estado="activa",
        inicio=timezone.localdate(),
        fin=None,
        payment_status="trial" if plan.trial_days > 0 else "unpaid",
    )
    if plan.trial_days > 0:
        # No persistimos nada extra aquí; UI calcula trial_ends_at desde plan.trial_days
        logger.info(
            "Suscripción en TRIAL creada para %s con plan %s", empresa, plan)
    else:
        logger.info(
            "Suscripción creada (sin trial) para %s con plan %s", empresa, plan)

    return ServiceResult(ok=True, data={"suscripcion": sub})


# ---------------------------
# Cambio de plan
# ---------------------------

@transaction.atomic
def change_plan(*, empresa: Empresa, nuevo_plan: PlanSaaS, keep_window: bool = True) -> ServiceResult:
    """
    Cambia el plan de la suscripción de la empresa.

    Args:
        empresa: Empresa target.
        nuevo_plan: Plan destino.
        keep_window: Si True, conserva ventana [inicio, fin] tal como está.
                     Si False y el plan destino tiene trial_days>0 y la suscripción está 'unpaid',
                     puede reiniciar trial (política simple de onboarding/upgrade).

    Política MVP:
    - No se recalculan importes aquí (no hay pasarela).
    - Si keep_window=False y el nuevo plan tiene trial y la suscripción está "unpaid", colocamos status "trial".
      (Evita abusos: solo si venías impago y estás haciendo upgrade).
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError(
            "La empresa no tiene suscripción para cambiar de plan.")

    prev = sub.plan
    sub.plan = nuevo_plan

    if not keep_window and sub.payment_status == "unpaid" and nuevo_plan.trial_days > 0:
        sub.payment_status = "trial"   # reinicia período de trial a nivel de status/UI
        # La fecha de corte del trial se calcula en UI desde `inicio` + trial_days del plan nuevo.

    sub.save(update_fields=["plan", "payment_status", "actualizado_en"])
    logger.info("Cambio de plan: %s → %s (empresa=%s)",
                prev, nuevo_plan, empresa)
    return ServiceResult(ok=True, data={"suscripcion": sub})


# ---------------------------
# Renovaciones / Pagos (stubs de pasarela)
# ---------------------------

@transaction.atomic
def confirm_paid_cycle(*, empresa: Empresa, months: int = 1,
                       external_subscription_id: str | None = None,
                       external_customer_id: str | None = None,
                       external_plan_id: str | None = None) -> ServiceResult:
    """
    Marca un ciclo pago confirmado.
    - Actualiza payment_status='paid', last_payment_at, next_billing_at.
    - Extiende `fin` (vigencia funcional) ~ +30*months días (MVP).
    - Actualiza IDs externos si vienen del webhook.

    Se espera ser invocado desde un webhook handler de la pasarela.
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError("No existe suscripción para confirmar pago.")

    if external_subscription_id:
        sub.external_subscription_id = external_subscription_id
    if external_customer_id:
        sub.external_customer_id = external_customer_id
    if external_plan_id:
        sub.external_plan_id = external_plan_id

    sub.mark_paid_cycle(months=months)
    sub.save()
    logger.info("Pago confirmado: empresa=%s months=%s fin=%s",
                empresa, months, sub.fin)
    return ServiceResult(ok=True, data={"suscripcion": sub})


@transaction.atomic
def mark_unpaid(*, empresa: Empresa) -> ServiceResult:
    """
    Coloca payment_status='unpaid'. Útil cuando:
    - Expiró trial y no hubo pago.
    - Falló un cobro.
    No cambia 'estado' (eso lo decide política; ver `recompute_estado`).
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError("No existe suscripción.")
    sub.mark_unpaid()
    sub.save(update_fields=["payment_status", "actualizado_en"])
    logger.info("Suscripción marcada UNPAID: empresa=%s", empresa)
    return ServiceResult(ok=True, data={"suscripcion": sub})


@transaction.atomic
def suspend_subscription(*, empresa: Empresa, reason: str | None = None) -> ServiceResult:
    """
    Suspensión funcional (estado='suspendida').
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError("No existe suscripción.")
    sub.mark_suspended()
    sub.save(update_fields=["estado", "actualizado_en"])
    logger.warning(
        "Suscripción SUSPENDIDA: empresa=%s reason=%s", empresa, reason)
    return ServiceResult(ok=True, data={"suscripcion": sub})


@transaction.atomic
def activate_subscription(*, empresa: Empresa) -> ServiceResult:
    """
    Reactiva funcionalmente (estado='activa'), sin modificar fechas.
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError("No existe suscripción.")
    sub.mark_active()
    sub.save(update_fields=["estado", "actualizado_en"])
    logger.info("Suscripción ACTIVADA: empresa=%s", empresa)
    return ServiceResult(ok=True, data={"suscripcion": sub})


# ---------------------------
# Recomputar estado por fechas
# ---------------------------

@transaction.atomic
def recompute_estado(*, empresa: Empresa) -> ServiceResult:
    """
    Si hoy > fin y no está suspendida, marca 'vencida'.
    No cambia payment_status; eso lo gestiona la pasarela o lógica de cobro.
    """
    sub = suscripcion_de(empresa)
    if not sub:
        raise ServiceError("No existe suscripción.")
    prev = sub.estado
    sub.mark_expired_if_needed()
    if sub.estado != prev:
        sub.save(update_fields=["estado", "actualizado_en"])
        logger.info("Estado recomputado: %s → %s (empresa=%s)",
                    prev, sub.estado, empresa)
    return ServiceResult(ok=True, data={"suscripcion": sub})
