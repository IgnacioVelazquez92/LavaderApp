# apps/app_log/logging_filters.py
from __future__ import annotations
import logging
from .utils import get_current_request


class RequestContextFilter(logging.Filter):
    """
    Añade campos al record para poder usarlos en el formatter:
    %(username)s %(empresa_id)s %(request_id)s %(method)s %(path)s %(status)s %(duration_ms)s
    """

    def filter(self, record: logging.LogRecord) -> bool:
        req = get_current_request()
        # Valores por defecto
        record.username = "-"
        record.empresa_id = "-"
        record.request_id = "-"
        record.method = "-"
        record.path = "-"
        record.status = "-"
        record.duration_ms = "-"
        if req:
            user = getattr(req, "user", None)
            if getattr(user, "is_authenticated", False):
                record.username = getattr(user, "username", None) or str(
                    getattr(user, "id", "-"))
            empresa = getattr(req, "empresa_activa", None)
            record.empresa_id = str(getattr(empresa, "id", "-") or "-")
            record.request_id = str(getattr(req, "request_id", "-") or "-")
            record.method = getattr(req, "method", "-") or "-"
            record.path = getattr(req, "path", "-") or "-"
            # Estos 2 campos los inyectamos desde RequestLogMiddleware.meta si existen
            # Para no romper, dejamos '-' si no están
            # Podés también setearlos en record extra al logear manualmente.
        return True
