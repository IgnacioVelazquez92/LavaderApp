# apps/app_log/logging_handler.py
"""
Handler de logging que envía registros a AppLog.
Usa importación perezosa para evitar tocar models antes de que Django esté listo.
Tolera arranques sin migraciones aplicadas.
"""

import logging


class AppLogDBHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            # Import perezoso: evita cargar models/servicios antes de tiempo
            from django.core.exceptions import ImproperlyConfigured
            from django.apps import apps
            if not apps.ready:
                return  # Aún no está listo el registry → no logueamos a DB

            # Import acá dentro para no romper la configuración temprana
            from .services.logger import log_event

            level = (record.levelname or "INFO").lower()
            msg = self.format(
                record) if self.formatter else record.getMessage()
            meta = {
                "logger": record.name,
                "pathname": record.pathname,
                "lineno": record.lineno,
                "funcName": record.funcName,
                "exc_text": record.exc_text,
            }

            # Intentá guardar. Si la tabla no existe todavía (primer migrate), ignorá.
            try:
                log_event(
                    nivel=level,
                    origen=record.name,
                    evento="django_log",
                    mensaje=msg,
                    meta=meta,
                )
            except Exception:
                # Casos típicos: OperationalError (tabla no existe), AppRegistryNotReady, etc.
                pass

        except Exception:
            # Nunca romper el flujo de logging por errores del handler
            pass
