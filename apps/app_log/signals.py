# apps/app_log/signals.py
"""
Señales de auditoría automática (CRUD) para modelos de negocio.

Qué hace:
- Captura snapshots BEFORE en pre_save y AFTER en post_save.
- Difere valores y guarda un AuditLog con action=create|update.
- En post_delete guarda snapshot_before y action=delete.
- Detecta soft delete/restauración si el modelo tiene campos comunes
  (is_deleted / deleted / deleted_at) y registra SOFT_DELETE/RESTORE.

Cómo activar:
- Agregar "apps.app_log" a INSTALLED_APPS.
- En apps.py (AppLogConfig.ready) se importa este módulo.
- Definir en settings:
    AUDIT_TRACKED_MODELS = ["sales.Venta", "payments.Pago", ...]
    AUDIT_EXCLUDE_FIELDS = ["id","creado_en","actualizado_en","created_at","updated_at"]

Notas:
- Las operaciones bulk_* (bulk_create/update/delete) NO disparan señales.
  Para esos casos, auditar desde servicios explícitos.
- Evitá incluir PII innecesaria en snapshots/cambios.
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

# Logger para enviar eventos de auditoría a archivos .log
audit_logger = logging.getLogger("apps.audit")


def _k(instance) -> str:
    return f"{instance._meta.label_lower}:{instance.pk}"


def _is_tracked(instance) -> bool:
    return instance._meta.label in AUDIT_TRACKED_MODELS or (
        instance._meta.label_lower in AUDIT_TRACKED_MODELS
    )


def _serialize_value(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, UUID):
        return str(v)
    return v


def _serialize_instance(instance) -> Dict[str, Any]:
    data = model_to_dict(instance)
    for k, v in list(data.items()):
        data[k] = _serialize_value(v)
    return data


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    changes: Dict[str, Dict[str, Any]] = {}
    keys = set(before.keys()) | set(after.keys())
    for k in keys:
        if k in AUDIT_EXCLUDE_FIELDS:
            continue
        if before.get(k) != after.get(k):
            changes[k] = {"before": before.get(k), "after": after.get(k)}
    return changes


def _request_context():
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
    }
    return ctx


def _detect_soft_delete(before: Dict[str, Any], after: Dict[str, Any]) -> str | None:
    flags = [("is_deleted", bool), ("deleted", bool)]
    ts_fields = ["deleted_at"]

    for name, _ in flags:
        if name in before or name in after:
            b = bool(before.get(name))
            a = bool(after.get(name))
            if b is False and a is True:
                return AuditLog.Action.SOFT_DELETE
            if b is True and a is False:
                return AuditLog.Action.RESTORE

    for name in ts_fields:
        if name in before or name in after:
            b = before.get(name)
            a = after.get(name)
            if (b in (None, "", 0)) and a not in (None, "", 0):
                return AuditLog.Action.SOFT_DELETE
            if b not in (None, "", 0) and (a in (None, "", 0)):
                return AuditLog.Action.RESTORE

    return None


@receiver(pre_save)
def _capture_before(sender, instance, **kwargs):
    if not _is_tracked(instance) or not instance.pk:
        return
    try:
        prev = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    _before_cache[_k(instance)] = _serialize_instance(prev)


@receiver(post_save)
def _audit_save(sender, instance, created, **kwargs):
    if not _is_tracked(instance):
        return

    ctx = _request_context()
    after = _serialize_instance(instance)

    if created:
        action = AuditLog.Action.CREATE
        AuditLog.objects.create(
            action=action,
            resource_type=instance._meta.label,
            resource_id=str(instance.pk),
            snapshot_after=after,
            changes={k: {"before": None, "after": v}
                     for k, v in after.items() if k not in AUDIT_EXCLUDE_FIELDS},
            success=True,
            **ctx,
        )
        # Log también en archivo
        audit_logger.info(
            "audit event",
            extra={"action": action, "resource_type": instance._meta.label,
                   "resource_id": str(instance.pk), "success": True},
        )
        return

    before = _before_cache.pop(_k(instance), {})
    changes = _diff(before, after)
    soft = _detect_soft_delete(before, after)
    action = soft if soft else AuditLog.Action.UPDATE

    AuditLog.objects.create(
        action=action,
        resource_type=instance._meta.label,
        resource_id=str(instance.pk),
        snapshot_before=before,
        snapshot_after=after,
        changes=changes,
        success=True,
        **ctx,
    )
    audit_logger.info(
        "audit event",
        extra={"action": action, "resource_type": instance._meta.label,
               "resource_id": str(instance.pk), "success": True},
    )


@receiver(post_delete)
def _audit_delete(sender, instance, **kwargs):
    if not _is_tracked(instance):
        return

    ctx = _request_context()
    before = _serialize_instance(instance)

    AuditLog.objects.create(
        action=AuditLog.Action.DELETE,
        resource_type=instance._meta.label,
        resource_id=str(instance.pk),
        snapshot_before=before,
        success=True,
        **ctx,
    )
    audit_logger.info(
        "audit event",
        extra={"action": AuditLog.Action.DELETE, "resource_type": instance._meta.label,
               "resource_id": str(instance.pk), "success": True},
    )
