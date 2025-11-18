# apps/cashbox/services/guards.py
"""
Guardas/validaciones reutilizables para Turnos de Caja.

Compatibilidad:
- API previa:
    - ensure_no_turno_abierto(...)
    - ensure_turno_abierto(...)
    - TurnoInexistenteError / TurnoExistenteError
- API nueva:
    - get_turno_abierto(empresa, sucursal)
    - require_turno_abierto(empresa, sucursal)
    - SinTurnoAbierto (subclase de TurnoInexistenteError)

Criterio:
- Enforcement mínimo a nivel sucursal: alcanza con que haya *algún* turno abierto
  en la sucursal (no necesariamente del mismo usuario). Para enforcement por-usuario,
  usá los helpers ensure_* con usuario=...
"""

from __future__ import annotations

from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.cashbox.models import TurnoCaja


# ===========================
# Jerarquía de errores (compat)
# ===========================

class TurnoError(ValidationError):
    """Base de errores de turnos de caja (compatible con flujos de forms/UX)."""
    pass


class TurnoInexistenteError(TurnoError):
    """No se encontró turno abierto (según la política aplicada)."""
    pass


class SinTurnoAbierto(TurnoInexistenteError):
    """
    Alias semántico moderno para 'no hay turno abierto'.
    Hereda de TurnoInexistenteError para compatibilidad hacia atrás.
    """
    pass


class TurnoExistenteError(TurnoError):
    """Se intentó abrir un turno nuevo pero ya hay uno abierto."""
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
    Retorna el turno abierto o lanza SinTurnoAbierto (subclase de TurnoInexistenteError).
    Recomendado para coherencia de caja en vistas de ventas/pagos.
    """
    turno = get_turno_abierto(empresa, sucursal)
    if not turno:
        raise SinTurnoAbierto(
            _("Debés abrir un turno de caja para esta sucursal."))
    return turno


# ===========================
# API previa (compatibilidad)
# ===========================

def ensure_no_turno_abierto(*, empresa, sucursal, usuario=None) -> bool:
    """
    Verifica que NO exista un turno abierto.
    - Si `usuario` se provee → verificación por-usuario (abierto_por=usuario).
    - Si `usuario` es None → verificación por sucursal (cualquier usuario).
    Lanza TurnoExistenteError si encuentra uno abierto.
    """
    qs = TurnoCaja.objects.filter(
        empresa=empresa,
        sucursal=sucursal,
        cerrado_en__isnull=True,
    )
    if usuario is not None:
        # Ajustar al nombre real del campo si difiere
        qs = qs.filter(abierto_por=usuario)

    if qs.exists():
        raise TurnoExistenteError(
            _("Ya hay un turno abierto en esta sucursal."))
    return True


def ensure_turno_abierto(*, empresa, sucursal, usuario=None) -> TurnoCaja:
    """
    Verifica que exista un turno abierto.
    - Con `usuario` → busca turno abierto de ese usuario, sino TurnoInexistenteError.
    - Sin `usuario` → alcanza con *algún* turno abierto en la sucursal.
    Devuelve el turno encontrado.
    """
    qs = TurnoCaja.objects.filter(
        empresa=empresa,
        sucursal=sucursal,
        cerrado_en__isnull=True,
    )

    if usuario is not None:
        turno = qs.filter(abierto_por=usuario).order_by("-abierto_en").first()
        if not turno:
            raise TurnoInexistenteError(
                _("No tenés un turno abierto. Debés habilitar tu turno antes de operar.")
            )
        return turno

    turno = qs.order_by("-abierto_en").first()
    if not turno:
        # Usamos SinTurnoAbierto (subclase de TurnoInexistenteError) para mantener compat
        raise SinTurnoAbierto(_("No hay un turno abierto para esta sucursal."))
    return turno


def ensure_empresa_habilitada_para_turnos(*, empresa) -> bool:
    """
    Placeholder para control de suscripciones/planes SaaS.
    Si tu modelo de suscripción define flags, validalos acá.
    """
    plan = getattr(empresa, "suscripcion", None)
    if plan and hasattr(plan, "permite_turnos_caja") and not plan.permite_turnos_caja:
        raise TurnoError(
            _("Tu plan actual no incluye el módulo de caja / turnos."))
    return True
