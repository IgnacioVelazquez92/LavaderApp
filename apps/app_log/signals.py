# apps/app_log/signals.py
"""
Señales de auditoría automática (CRUD) para modelos de negocio.

Qué hace:
- Captura snapshot BEFORE en pre_save y AFTER en post_save.
- Calcula difs y guarda un AuditLog con action=create|update.
- En post_delete guarda snapshot_before y action=delete.
- Detecta soft delete/restauración si el modelo tiene campos comunes
  (is_deleted / deleted / deleted_at) y registra SOFT_DELETE/RESTORE.
- Además, emite un log a archivo (logger "apps.audit") para que quede
  rastro en los .log por usuario/día.

Cómo activar:
- Agregar "apps.app_log" a INSTALLED_APPS.
- En apps.py (AppLogConfig.ready) se importa este módulo.
- Definir en settings:
    AUDIT_TRACKED_MODELS = ["sales.Venta", "payments.Pago", ...]
    AUDIT_EXCLUDE_FIELDS = ["id","creado_en","actualizado_en","created_at","updated_at"]

Notas:
- Las operaciones bulk_* (bulk_create/update/delete) NO disparan señales.
  Para esos casos, auditar desde servicios explícitos.
- Evitá incluir PII innecesaria en snapshots/cambios (sanitizá en servicios).
"""

from __future__ import annotations

from typing import Any, Dict
from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
import logging

from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.forms.models import model_to_dict
from django.dispatch import receiver

from .models import AuditLog
from .utils import get_current_request

# Config desde settings
AUDIT_TRACKED_MODELS = set(getattr(settings, "AUDIT_TRACKED_MODELS", []))
AUDIT_EXCLUDE_FIELDS = set(
    getattr(
        settings,
        "AUDIT_EXCLUDE_FIELDS",
        ["id", "creado_en", "actualizado_en", "created_at", "updated_at"],
    )
)

# Cache temporal de snapshots BEFORE por instancia (clave: "<label_lower>:<pk>")
_before_cache: Dict[str, Dict[str, Any]] = {}

# Logger para enviar eventos de auditoría también a archivos .log
audit_logger = logging.getLogger("apps.audit")


def _k(instance) -> str:
    return f"{instance._meta.label_lower}:{instance.pk}"


def _is_tracked(instance) -> bool:
    """
    Evalúa si el modelo está en la lista de seguimiento.
    Admite label y label_lower para conveniencia.
    """
    return instance._meta.label in AUDIT_TRACKED_MODELS or (
        instance._meta.label_lower in AUDIT_TRACKED_MODELS
    )


def _serialize_value(v: Any) -> Any:
    """Serializa valores no JSON-compatibles a str simple."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, UUID):
        return str(v)
    return v


def _serialize_instance(instance) -> Dict[str, Any]:
    """
    Serializa el modelo a un dict plano (model_to_dict) y normaliza
    valores problemáticos (Decimal, datetime, UUID) a strings.
    """
    data = model_to_dict(instance)
    for k, v in list(data.items()):
        data[k] = _serialize_value(v)
    return data


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Calcula diferencias campo a campo excluyendo los campos ignorados.
    """
    changes: Dict[str, Dict[str, Any]] = {}
    keys = set(before.keys()) | set(after.keys())
    for k in keys:
        if k in AUDIT_EXCLUDE_FIELDS:
            continue
        if before.get(k) != after.get(k):
            changes[k] = {"before": before.get(k), "after": after.get(k)}
    return changes


def _request_context() -> Dict[str, Any]:
    """
    Extrae contexto del request actual (si existe) para guardar en AuditLog
    y para enriquecer el log a archivos (apps.audit).
    """
    req = get_current_request()
    if not req:
        return {}
    user = getattr(req, "user", None)
    ctx = {
        "empresa_id": getattr(getattr(req, "empresa_activa", None), "id", None)
        or getattr(req, "empresa_activa", None),
        "user_id": getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None,
        "username": getattr(user, "username", None) if getattr(user, "is_authenticated", False) else None,
        "ip": req.META.get("REMOTE_ADDR"),
        "user_agent": req.META.get("HTTP_USER_AGENT"),
        "request_id": str(getattr(req, "request_id", "")) or None,
        # si implementaste parent_request_id en middleware:
        "parent_request_id": str(getattr(req, "parent_request_id", "")) or None,
    }
    return ctx


def _detect_soft_delete(before: Dict[str, Any], after: Dict[str, Any]) -> str | None:
    """
    Heurística simple para detectar soft delete / restore en modelos que
    tengan banderas/campos típicos:
    - booleanos: is_deleted / deleted
    - timestamp: deleted_at

    Devuelve "soft_delete" | "restore" | None
    """
    flags = [("is_deleted", bool), ("deleted", bool)]
    ts_fields = ["deleted_at"]

    # Flag booleano
    for name, _ in flags:
        if name in before or name in after:
            b = bool(before.get(name))
            a = bool(after.get(name))
            if b is False and a is True:
                return AuditLog.Action.SOFT_DELETE
            if b is True and a is False:
                return AuditLog.Action.RESTORE

    # Timestamp
    for name in ts_fields:
        if name in before or name in after:
            b = before.get(name)
            a = after.get(name)
            if (b in (None, "", 0)) and a not in (None, "", 0):
                return AuditLog.Action.SOFT_DELETE
            if b not in (None, "", 0) and (a in (None, "", 0)):
                return AuditLog.Action.RESTORE

    return None


def _emit_audit_file_log(action: str, instance, success: bool, changes_count: int, ctx: Dict[str, Any]):
    """
    Emite un renglón a los .log por usuario/día (logger 'apps.audit').
    Usa 'extra' para que el RequestContextFilter/handlers sumen contexto.
    """
    try:
        audit_logger.info(
            f"audit {action} {instance._meta.label} id={instance.pk} success={success} changes={changes_count}",
            extra={
                # contexto del recurso
                "resource_type": instance._meta.label,
                "resource_id": str(instance.pk),
                "action": action,
                "success": success,
                "changes_count": changes_count,
                # contexto de request/tenant/usuario (por si no hay request activo,
                # el filtro también intenta completarlo)
                "empresa_id": ctx.get("empresa_id"),
                "user_id": ctx.get("user_id"),
                "username": ctx.get("username"),
                "request_id": ctx.get("request_id"),
                "parent_request_id": ctx.get("parent_request_id"),
            },
        )
    except Exception:
        # Nunca romper el flujo de señales por problemas de logging
        pass


def _create_audit_log(action: str, instance, before: Dict[str, Any] | None, after: Dict[str, Any] | None, changes: Dict[str, Any] | None, ctx: Dict[str, Any]):
    """
    Crea el registro de auditoría en DB de forma segura.
    """
    try:
        payload = {
            "action": action,
            "resource_type": instance._meta.label,
            "resource_id": str(instance.pk),
            "success": True,
            **ctx,
        }
        if before is not None:
            payload["snapshot_before"] = before
        if after is not None:
            payload["snapshot_after"] = after
        if changes is not None:
            payload["changes"] = changes

        AuditLog.objects.create(**payload)
    except Exception:
        # Nunca romper por auditoría. Podés agregar aquí un log_event error si querés.
        pass


@receiver(pre_save)
def _capture_before(sender, instance, **kwargs):
    """
    Guarda snapshot BEFORE para updates.
    """
    if not _is_tracked(instance) or not instance.pk:
        return
    try:
        prev = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    _before_cache[_k(instance)] = _serialize_instance(prev)


@receiver(post_save)
def _audit_save(sender, instance, created, **kwargs):
    """
    Crea un AuditLog en create/update con diffs y snapshots.
    Detecta soft delete / restore si corresponde.
    Además escribe un renglón en los archivos .log (apps.audit).
    """
    if not _is_tracked(instance):
        return

    ctx = _request_context()
    after = _serialize_instance(instance)

    if created:
        action = AuditLog.Action.CREATE
        # changes sintéticos: before=None → after=valor
        changes = {
            k: {"before": None, "after": v}
            for k, v in after.items() if k not in AUDIT_EXCLUDE_FIELDS
        }

        _create_audit_log(action, instance, before=None,
                          after=after, changes=changes, ctx=ctx)
        _emit_audit_file_log(action, instance, success=True,
                             changes_count=len(changes), ctx=ctx)
        return

    # UPDATE
    before = _before_cache.pop(_k(instance), {})
    changes = _diff(before, after)

    soft = _detect_soft_delete(before, after)
    action = soft if soft else AuditLog.Action.UPDATE

    _create_audit_log(action, instance, before=before,
                      after=after, changes=changes, ctx=ctx)
    _emit_audit_file_log(action, instance, success=True,
                         changes_count=len(changes), ctx=ctx)


@receiver(post_delete)
def _audit_delete(sender, instance, **kwargs):
    """
    Crea un AuditLog DELETE con snapshot_before.
    También emite línea a archivos .log (apps.audit).
    """
    if not _is_tracked(instance):
        return

    ctx = _request_context()
    before = _serialize_instance(instance)

    _create_audit_log(AuditLog.Action.DELETE, instance,
                      before=before, after=None, changes=None, ctx=ctx)
    _emit_audit_file_log(AuditLog.Action.DELETE, instance,
                         success=True, changes_count=0, ctx=ctx)
