# apps/app_log/logging_filters.py
from __future__ import annotations
import logging
from .utils import get_current_request

SANITIZE_KEYS = {"password", "token", "authorization",
                 "cookie", "secret", "apikey", "api_key"}


def _redact(d: dict) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        lk = str(k).lower()
        out[k] = "***redacted***" if any(s in lk for s in SANITIZE_KEYS) else v
    return out


class RequestContextFilter(logging.Filter):
    """
    Añade campos al record para usarlos en formatters/handlers:
    %(username)s %(empresa_id)s %(request_id)s %(parent_request_id)s
    %(method)s %(path)s %(status)s %(duration_ms)s %(redirect_to)s
    %(route_name)s %(template_name)s %(messages)s %(body_preview)s
    """

    def filter(self, record: logging.LogRecord) -> bool:
        req = get_current_request()
        # Defaults
        record.username = getattr(record, "username", "-")
        record.empresa_id = getattr(record, "empresa_id", "-")
        record.request_id = getattr(record, "request_id", "-")
        record.parent_request_id = getattr(record, "parent_request_id", "-")
        record.method = getattr(record, "method", "-")
        record.path = getattr(record, "path", "-")
        record.status = getattr(record, "status", "-")
        record.duration_ms = getattr(record, "duration_ms", "-")
        record.redirect_to = getattr(record, "redirect_to", None)
        record.route_name = getattr(record, "route_name", None)
        record.template_name = getattr(record, "template_name", None)
        record.messages = getattr(record, "messages", None)
        record.body_preview = getattr(record, "body_preview", None)

        if req:
            user = getattr(req, "user", None)
            if getattr(user, "is_authenticated", False):
                record.username = getattr(user, "username", None) or str(
                    getattr(user, "id", "-"))
            empresa = getattr(req, "empresa_activa", None)
            record.empresa_id = str(getattr(empresa, "id", "-") or "-")
            record.request_id = str(getattr(req, "request_id", "-") or "-")
            record.parent_request_id = str(
                getattr(req, "parent_request_id", "-") or "-")
            record.method = getattr(req, "method", "-") or "-"
            record.path = getattr(req, "path", "-") or "-"

            # Si desde el middleware se adjuntaron estos extras en record, los conservamos:
            # status, duration_ms, redirect_to, route_name, template_name, messages, body_preview

        # Sanitizar mensajes/payload si vienen como dict/list
        if isinstance(record.messages, list):
            try:
                record.messages = [{"level": m.get("level"), "message": str(
                    m.get("message"))} for m in record.messages]
            except Exception:
                pass
        if isinstance(record.body_preview, dict):
            record.body_preview = _redact(record.body_preview)

        return True
