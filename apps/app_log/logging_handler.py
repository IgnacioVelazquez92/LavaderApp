# apps/app_log/logging_handler.py
"""
Handler de logging que envía registros a AppLog.
Usa importación perezosa para evitar tocar models antes de que Django esté listo.
Tolera arranques sin migraciones aplicadas.
"""

import logging


class AppLogDBHandler(logging.Handler):
    """
    Handler que envía logs Python/Django a AppLog (BD).
    Copia atributos del record incluidos por RequestContextFilter y por 'extra'.
    Tolera arranque sin apps ready ni tablas.
    """

    def emit(self, record: logging.LogRecord):
        try:
            from django.apps import apps
            if not apps.ready:
                return
            from .services.logger import log_event

            level = (record.levelname or "INFO").lower()
            msg = self.format(
                record) if self.formatter else record.getMessage()

            # Meta base
            meta = {
                "logger": record.name,
                "pathname": getattr(record, "pathname", None),
                "lineno": getattr(record, "lineno", None),
                "funcName": getattr(record, "funcName", None),
                "exc_text": getattr(record, "exc_text", None),
            }

            # Extras enriquecidos (si existen)
            for attr in (
                "method", "path", "status", "duration_ms",
                "request_id", "parent_request_id",
                "username", "empresa_id",
                "redirect_to", "route_name", "template_name",
                "messages", "body_preview",
            ):
                val = getattr(record, attr, None)
                if val not in (None, "-", ""):
                    meta[attr] = val

            log_event(
                nivel=level,
                origen=record.name,
                evento="django_log",
                mensaje=msg,
                meta=meta,
            )
        except Exception:
            # Nunca romper el flujo de logging
            pass
