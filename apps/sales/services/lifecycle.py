# apps/sales/services/lifecycle.py
"""
Hooks de ciclo de vida de la Venta.
Se disparan DESPUÉS de una transición de estado de PROCESO o de cambios de PAGO.
No cambian FSM ni payment_status; solo side-effects.
"""

from __future__ import annotations

import logging
from django.conf import settings

from apps.sales.models import Venta

logger = logging.getLogger(__name__)


# -----------------------------
# Hooks del PROCESO (estado)
# -----------------------------

def on_iniciar(venta: Venta, prev_estado: str | None = None, actor=None) -> None:
    """
    Se ejecuta cuando la venta pasa a 'en_proceso'.
    Ej.: auditar inicio, asignaciones, notificaciones internas, etc.
    """
    logger.info("Venta %s iniciada (en_proceso). Prev: %s",
                venta.id, prev_estado)


def on_finalizar(venta: Venta, prev_estado: str | None = None, actor=None) -> None:
    """
    Se ejecuta cuando la venta pasa a 'terminado'.
    Ej.: disparar notificación 'vehículo listo' (si luego se confirma), auditar, etc.
    """
    logger.info("Venta %s finalizada (terminado). Prev: %s",
                venta.id, prev_estado)


def on_cancelar(venta: Venta, prev_estado: str | None = None, actor=None) -> None:
    """
    Se ejecuta cuando la venta pasa a 'cancelado'.
    """
    logger.info("Venta %s cancelada. Prev: %s", venta.id, prev_estado)


# --------------------------------
# Hooks del PAGO (payment_status)
# --------------------------------

def on_pagada(venta: Venta, prev_payment_status: str | None = None, actor=None) -> None:
    """
    Se ejecuta cuando la venta queda con payment_status='pagada'.
    Si INVOICING_AUTO_EMIT_ON_PAID=True → intenta auto-emitir comprobante,
    siempre que la venta NO esté cancelada.

    No rompe el flujo: cualquier error se loguea.
    """
    if venta.payment_status != "pagada":
        # Defensa; solo aplica si efectivamente está pagada.
        logger.debug(
            "on_pagada llamado pero payment_status=%s (venta %s).",
            venta.payment_status, venta.id
        )
        return

    if venta.estado == "cancelado":
        logger.info(
            "Venta %s está cancelada; se omite auto-emisión de comprobante.", venta.id
        )
        return

    auto_emit = getattr(settings, "INVOICING_AUTO_EMIT_ON_PAID", False)
    if not auto_emit:
        logger.info(
            "Venta %s pagada. Auto-emisión desactivada (INVOICING_AUTO_EMIT_ON_PAID=False). Prev payment_status=%s",
            venta.id, prev_payment_status,
        )
        return

    try:
        # Idempotente: no emite si ya existe un comprobante válido.
        from apps.invoicing.services.emit import emitir_auto
        res = emitir_auto(venta_id=venta.id, actor=actor)
        if res is None:
            logger.info(
                "Venta %s: ya tenía comprobante o no aplicaba auto-emisión.", venta.id
            )
        else:
            logger.info(
                "Venta %s: comprobante auto-emitido %s.",
                venta.id, res.comprobante.numero_completo
            )
    except Exception as exc:
        logger.exception(
            "Auto-emisión fallida para venta %s: %s", venta.id, exc)
