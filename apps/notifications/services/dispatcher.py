# apps/notifications/services/dispatcher.py
"""
Dispatcher/orquestador de envíos de notificaciones.

Responsabilidades:
- Validar precondiciones de negocio:
    * Venta debe pertenecer a la empresa activa (validación típica en la vista).
    * Estado habilitante: SOLO enviar cuando la venta está "terminado".
    * Plantilla activa y del mismo tenant.
    * Destinatario válido según canal (email o E.164 para WhatsApp).
- Renderizar asunto/cuerpo con `renderers.render`.
- Enviar:
    * EMAIL: envío REAL vía EmailServer (SMTP) de la empresa.
    * WHATSAPP: simulado (deep link a WhatsApp Web).
- Persistir `LogNotif` con estado ENVIADO o ERROR.

Decisiones:
- Sin idempotencia obligatoria (campo opcional `idempotency_key` guardado si se pasa).
- Validaciones de formato simples: suficiente para MVP (pueden endurecerse luego).
"""

from __future__ import annotations
from urllib.parse import quote
import re
import traceback
from typing import Any, Mapping

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from ..models import LogNotif, PlantillaNotif, Canal, EstadoEnvio, EmailServer
from . import renderers
from .smtp import build_backend_from_emailserver


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
                "El teléfono WhatsApp debe estar en formato E.164 (ej. +549381XXXXXXX)."
            )
    else:
        raise NotificationError(f"Canal no soportado: {canal!r}.")


def _venta_habilitada_para_enviar(venta) -> bool:
    """Regla de negocio acordada: SOLO cuando la venta está 'terminado'."""
    return getattr(venta, "estado", None) == "terminado"


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
    # Alternativa:
    # return f"https://wa.me/{phone.lstrip('+')}?text={encoded}"


def _get_active_email_server(empresa) -> EmailServer | None:
    """
    Retorna el EmailServer ACTIVO más reciente para la empresa.
    Si quisieras otra política (round-robin/peso), cambiar aquí.
    """
    return (
        EmailServer.objects.filter(empresa=empresa, activo=True)
        .order_by("-updated_at")
        .first()
    )


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
    3) Envío real (EMAIL) o simulado (WHATSAPP).
    4) Persistencia del LogNotif con estado.
    """
    # Tenant: plantilla y venta deben ser de la misma empresa
    if not venta or not plantilla or venta.empresa_id != plantilla.empresa_id:
        raise NotificationError(
            "Empresa de la plantilla y la venta no coinciden.")

    # Regla de estado habilitante
    if not _venta_habilitada_para_enviar(venta):
        raise NotificationError(
            "Solo se puede notificar cuando la venta está en estado TERMINADO."
        )

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

    # Render asunto/cuerpo con contexto
    render_result = renderers.render(plantilla, venta, extras=extras)
    asunto = render_result.asunto or "Notificación"
    cuerpo = render_result.cuerpo

    # Creamos el log en estado "PENDIENTE" (o lo podés crear directo como ENVIADO en tu diseño)
    log = LogNotif.objects.create(
        empresa=venta.empresa,
        venta=venta,
        plantilla=plantilla,
        canal=canal,
        destinatario=destinatario.strip(),
        asunto_renderizado=asunto or "",
        cuerpo_renderizado=cuerpo,
        estado=EstadoEnvio.PENDIENTE if hasattr(
            EstadoEnvio, "PENDIENTE") else EstadoEnvio.ENVIADO,
        error_msg="",
        idempotency_key=(idempotency_key or ""),
        meta={"contexto": render_result.contexto, **(extras or {})},
        creado_por=actor,
    )

    # Proceso de envío
    try:
        if canal == Canal.EMAIL:
            srv = _get_active_email_server(venta.empresa)
            if not srv:
                raise NotificationError(
                    "No hay un servidor SMTP activo configurado para la empresa.")

            backend = build_backend_from_emailserver(srv)
            from_email = srv.remitente_por_defecto or None

            msg = EmailMessage(
                subject=asunto,
                body=cuerpo or "",
                from_email=from_email,
                to=[destinatario],
                connection=backend,
            )
            # autodetecta HTML simple
            if "</" in (cuerpo or ""):
                msg.content_subtype = "html"

            sent = msg.send(fail_silently=False)
            if sent < 1:
                raise NotificationError(
                    "El backend SMTP no reportó destinatarios aceptados.")

            log.estado = EstadoEnvio.ENVIADO
            # Si tu modelo tiene timestamp enviado_en, setear aquí:
            # log.enviado_en = timezone.now()
            log.meta = {
                **(log.meta or {}),
                "backend": "smtp",
                "server": srv.host,
                "port": srv.port,
                "enviado_en": timezone.now().isoformat(),
            }
            log.save()

        elif canal == Canal.WHATSAPP:
            # Simulación: generamos URL y consideramos "enviado"
            wpp_url = build_whatsapp_web_url(destinatario, cuerpo or asunto)
            log.estado = EstadoEnvio.ENVIADO
            log.meta = {
                **(log.meta or {}),
                "backend": "whatsapp_web_sim",
                "url": wpp_url,
                "enviado_en": timezone.now().isoformat(),
            }
            log.save()

        else:
            raise NotificationError(f"Canal no soportado: {canal!r}")

    except Exception as e:
        # Cualquier excepción pasa a ERROR con detalle
        log.estado = EstadoEnvio.ERROR
        log.error_msg = str(e)[:800]
        log.meta = {
            **(log.meta or {}),
            "trace": traceback.format_exc()[-1200:],
            "fallo_en": timezone.now().isoformat(),
        }
        log.save()

    return log
