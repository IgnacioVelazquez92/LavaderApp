# ✅ Reemplazá COMPLETAMENTE el archivo por este contenido.
#    Así mantenemos tus helpers anteriores *y* agregamos los nuevos símbolos
#    que ya usan sales/payments (require_turno_abierto, SinTurnoAbierto).

# apps/cashbox/services/guards.py
"""
Guardas/validaciones reutilizables para Turnos de Caja.

Objetivos:
- Mantener compatibilidad con tus helpers previos:
    - ensure_no_turno_abierto(...)
    - ensure_turno_abierto(...)
    - ensure_empresa_habilitada_para_turnos(...)
- Agregar los símbolos que estamos importando desde sales/payments:
    - get_turno_abierto(empresa, sucursal)
    - require_turno_abierto(empresa, sucursal)
    - SinTurnoAbierto

Convenciones:
- A nivel de *enforcement mínimo* solemos exigir que exista *algún turno abierto*
  en la sucursal (no necesariamente del mismo usuario), para que el flujo de caja
  sea consistente con los pagos/ventas.
- Si querés enforcement por-usuario, usá los helpers `ensure_*` con `usuario=...`.
"""

from __future__ import annotations

from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.cashbox.models import TurnoCaja


# ===========================
# Excepciones públicas
# ===========================

class SinTurnoAbierto(Exception):
    """No hay un TurnoCaja abierto para la sucursal/empresa dada."""


class TurnoExistenteError(ValidationError):
    """Se intentó abrir un turno nuevo pero ya hay uno abierto (según la política aplicada)."""
    pass


class TurnoInexistenteError(ValidationError):
    """No se encontró turno abierto (según la política aplicada)."""
    pass


# ===========================
# API nueva (usada por sales/payments)
# ===========================

def get_turno_abierto(empresa, sucursal) -> Optional[TurnoCaja]:
    """
    Devuelve el turno abierto (si existe) para (empresa, sucursal).
    Si hubiera más de uno, retorna el más reciente.
    """
    if not (empresa and sucursal):
        return None
    return (
        TurnoCaja.objects
        .filter(empresa=empresa, sucursal=sucursal, cerrado_en__isnull=True)
        .order_by("-abierto_en")
        .first()
    )


def require_turno_abierto(empresa, sucursal) -> TurnoCaja:
    """
    Retorna el turno abierto sucursal/empresa o lanza SinTurnoAbierto si no existe.
    (Enforcement sucursal-level, recomendado para coherencia de caja.)
    """
    turno = get_turno_abierto(empresa, sucursal)
    if not turno:
        raise SinTurnoAbierto(
            _("Debés abrir un turno de caja para esta sucursal."))
    return turno


# ===========================
# API previa (compat)
# ===========================

def ensure_no_turno_abierto(*, empresa, sucursal, usuario=None) -> bool:
    """
    Verifica que NO exista un turno abierto.
    - Si `usuario` se provee → la verificación es por-usuario (abierto_por=usuario).
    - Si `usuario` es None → la verificación es por sucursal (cualquier usuario).
    Lanza TurnoExistenteError si encuentra uno abierto.
    """
    qs = TurnoCaja.objects.filter(
        empresa=empresa,
        sucursal=sucursal,
        cerrado_en__isnull=True,
    )
    # Si querés enforcement por usuario (opcional)
    if usuario is not None:
        # Ajustá a tu campo real de usuario en TurnoCaja (ej.: abierto_por)
        qs = qs.filter(abierto_por=usuario)

    if qs.exists():
        raise TurnoExistenteError(
            _("Ya hay un turno abierto en esta sucursal."))
    return True


def ensure_turno_abierto(*, empresa, sucursal, usuario=None) -> TurnoCaja:
    """
    Verifica que exista un turno abierto.
    - Si `usuario` se provee → intenta encontrar turno abierto de ese usuario.
      Si no existe, falla con TurnoInexistenteError.
    - Si `usuario` es None → alcanza con que haya *algún* turno abierto en la sucursal.
    Devuelve el turno encontrado.
    """
    qs = TurnoCaja.objects.filter(
        empresa=empresa,
        sucursal=sucursal,
        cerrado_en__isnull=True,
    )

    if usuario is not None:
        # Ajustá a tu campo real de usuario en TurnoCaja (ej.: abierto_por)
        turno = qs.filter(abierto_por=usuario).order_by("-abierto_en").first()
        if not turno:
            raise TurnoInexistenteError(
                _("No tenés un turno abierto. Debés habilitar tu turno antes de operar.")
            )
        return turno

    turno = qs.order_by("-abierto_en").first()
    if not turno:
        raise TurnoInexistenteError(
            _("No hay un turno abierto para esta sucursal."))
    return turno


def ensure_empresa_habilitada_para_turnos(*, empresa) -> bool:
    """
    Placeholder para control de suscripciones/planes SaaS.
    Si tu modelo de suscripción define flags, validalos acá.
    """
    plan = getattr(empresa, "suscripcion", None)
    # Cambiá el nombre del flag según tu modelo, o dejalo no restrictivo por ahora.
    if plan and hasattr(plan, "permite_turnos_caja") and not plan.permite_turnos_caja:
        raise ValidationError(
            _("Tu plan actual no incluye el módulo de caja / turnos."))
    return True
