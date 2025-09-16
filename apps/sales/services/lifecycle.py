# apps/sales/services/lifecycle.py
"""
Hooks de ciclo de vida de la Venta.
Se disparan DESPUÉS de una transición de estado.
No cambian FSM; solo side-effects.
"""

from __future__ import annotations

import logging
from django.conf import settings

from apps.sales.models import Venta

logger = logging.getLogger(__name__)


def on_finalizar(venta: Venta, actor=None) -> None:
    """
    Se ejecuta cuando la venta queda en 'terminado'.
    Ej.: notificar "vehículo listo", auditar, etc. (si aplica más tarde).
    """
    logger.info("Venta %s finalizada (terminado).", venta.id)


def on_pagada(venta: Venta, actor=None) -> None:
    """
    Se ejecuta cuando la venta queda en 'pagado'.
    Si INVOICING_AUTO_EMIT_ON_PAID=True → se intenta auto-emitir comprobante.
    Si False → no auto-emite (la UI mostrará el botón de Emisión).
    """
    auto_emit = getattr(settings, "INVOICING_AUTO_EMIT_ON_PAID", False)
    if not auto_emit:
        logger.info(
            "Venta %s pagada. Auto-emisión desactivada (INVOICING_AUTO_EMIT_ON_PAID=False).",
            venta.id,
        )
        return

    try:
        # Lógica idempotente y con defaults vive en invoicing.services.emit.emitir_auto
        from apps.invoicing.services.emit import emitir_auto
        res = emitir_auto(venta_id=venta.id, actor=actor)
        if res is None:
            # Ya había comprobante, o condiciones no dadas; no es error.
            logger.info(
                "Venta %s ya tenía comprobante o no aplicaba auto-emisión.", venta.id)
        else:
            logger.info(
                "Venta %s: comprobante auto-emitido %s.", venta.id, res.comprobante.numero_completo
            )
    except Exception as exc:
        # No rompemos el flujo de pago; solo log
        logger.exception(
            "Auto-emisión fallida para venta %s: %s", venta.id, exc)


def on_cancelar(venta: Venta, actor=None) -> None:
    """
    Se ejecuta cuando la venta queda en 'cancelado'.
    """
    logger.info("Venta %s cancelada.", venta.id)
