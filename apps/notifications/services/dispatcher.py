# apps/notifications/services/dispatcher.py
"""
Dispatcher/orquestador de envíos (simulados) de notificaciones.

Responsabilidades:
- Validar precondiciones de negocio:
    * Venta debe pertenecer a la empresa activa (validación típica en la vista).
    * Estado habilitante: SOLO enviar cuando la venta está "terminado".
    * Plantilla activa y del mismo tenant.
    * Destinatario válido según canal (email o E.164 para WhatsApp).
- Renderizar asunto/cuerpo con `renderers.render`.
- Simular el envío (MVP): NO integra proveedor; registra inmediatamente el LogNotif.
- Persistir `LogNotif` con estado ENVIADO o ERROR según validaciones.

Decisiones:
- Sin idempotencia obligatoria (campo opcional `idempotency_key` guardado si se pasa).
- Validaciones de formato simples: suficiente para MVP (pueden endurecerse luego).
"""

from __future__ import annotations
from urllib.parse import quote

import re
from typing import Any, Mapping

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import LogNotif, PlantillaNotif, Canal, EstadoEnvio
from . import renderers


EMAIL_RE = re.compile(r".+@.+\..+")
E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # ITU-T E.164, 7–15 dígitos


class NotificationError(Exception):
    """Error controlado de negocio para bloquear el envío."""


def _validate_recipient(canal: str, destinatario: str) -> None:
    """
    Valida el destinatario según canal.
    - email: usa validate_email (Django) + regex laxa de seguridad.
    - whatsapp: espera formato E.164 (+549... en AR, por ej.).
    """
    dest = (destinatario or "").strip()
    if not dest:
        raise NotificationError("El destinatario está vacío.")

    if canal == Canal.EMAIL:
        # validate_email ya es suficiente; regex de apoyo por si se deshabilita.
        try:
            validate_email(dest)
        except ValidationError:
            raise NotificationError("El email del destinatario no es válido.")
        if not EMAIL_RE.match(dest):
            raise NotificationError(
                "El email del destinatario no es válido (formato).")
    elif canal == Canal.WHATSAPP:
        if not E164_RE.match(dest):
            raise NotificationError(
                "El teléfono WhatsApp debe estar en formato E.164 (ej. +549381XXXXXXX).")
    else:
        raise NotificationError(f"Canal no soportado: {canal!r}.")


def _venta_habilitada_para_enviar(venta) -> bool:
    """
    Regla de negocio acordada: SOLO cuando la venta está 'terminado'.
    """
    return getattr(venta, "estado", None) == "terminado"


@transaction.atomic
def enviar_desde_venta(
    *,
    plantilla: PlantillaNotif,
    venta,
    destinatario: str | None = None,
    actor=None,
    extras: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> LogNotif:
    """
    Orquestación principal:
    1) Validaciones de negocio/tenant.
    2) Render asunto/cuerpo.
    3) Simulación de envío.
    4) Persistencia del LogNotif con estado.

    :param plantilla: PlantillaNotif activa y de la misma empresa que la venta.
    :param venta: instancia sales.Venta (se asume select_related en la vista).
    :param destinatario: email o E.164; si None, se infiere del cliente según canal.
    :param actor: User que ejecuta (para auditoría).
    :param extras: dict opcional (p.ej. {"nota_extra": "..."}).
    :param idempotency_key: opcional (guardado en el log; MVP no deduplica).
    :return: LogNotif creado.
    :raises NotificationError: si no cumple precondiciones.
    """
    # Tenant: plantilla y venta deben ser de la misma empresa
    if not venta or not plantilla or venta.empresa_id != plantilla.empresa_id:
        raise NotificationError(
            "Empresa de la plantilla y la venta no coinciden.")

    # Regla de estado habilitante
    if not _venta_habilitada_para_enviar(venta):
        raise NotificationError(
            "Solo se puede notificar cuando la venta está en estado TERMINADO.")

    # Plantilla activa
    if not plantilla.activo:
        raise NotificationError("La plantilla seleccionada está inactiva.")

    canal = plantilla.canal

    # Inferir destinatario si no se pasó
    if not destinatario:
        cliente = getattr(venta, "cliente", None)
        if canal == Canal.EMAIL:
            destinatario = getattr(cliente, "email", None)
        elif canal == Canal.WHATSAPP:
            destinatario = getattr(cliente, "tel_wpp", None)

    _validate_recipient(canal, destinatario)

    # Render asunto/cuerpo
    result = renderers.render(plantilla, venta, extras=extras)

    # Envío simulado (MVP): si quisiéramos simular fallas, aquí podría forzarse una condición.
    estado = EstadoEnvio.ENVIADO
    error_msg = ""

    # Persistir log
    log = LogNotif.objects.create(
        empresa=venta.empresa,
        venta=venta,
        plantilla=plantilla,
        canal=canal,
        destinatario=destinatario.strip(),
        asunto_renderizado=result.asunto or "",
        cuerpo_renderizado=result.cuerpo,
        estado=estado,
        error_msg=error_msg,
        idempotency_key=(idempotency_key or ""),
        meta={"contexto": result.contexto, **(extras or {})},
        creado_por=actor,
    )

    return log


def _to_text(value) -> str:
    """Normaliza cualquier valor a str UTF-8 (seguro para quote())."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def build_whatsapp_web_url(phone_e164: str, text) -> str:
    """
    Devuelve el deep link a WhatsApp Web con el mensaje prellenado.
    Acepta 'text' en str o bytes y lo normaliza a UTF-8 antes de url-encode.
    """
    phone = _to_text(phone_e164).strip()
    if not phone:
        return ""
    text_norm = _to_text(text)
    encoded = quote(text_norm, safe="")  # \n -> %0A; soporta emojis
    # api.whatsapp.com acepta "+549..."
    return f"https://api.whatsapp.com/send?phone={phone}&text={encoded}"
    # o si preferís wa.me:
    # return f"https://wa.me/{phone.lstrip('+')}?text={encoded}"
