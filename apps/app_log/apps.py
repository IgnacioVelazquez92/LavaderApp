# apps/app_log/apps.py
"""
Configuración de la aplicación app_log.
Engancha señales de auditoría automáticamente.
"""

from django.apps import AppConfig


class AppLogConfig(AppConfig):
    name = "apps.app_log"
    verbose_name = "Observabilidad (Logs + Auditoría)"

    def ready(self):
        # Importa señales para que se registren al iniciar Django
        from . import signals  # noqa: F401
