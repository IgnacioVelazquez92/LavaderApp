from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.app_log.models import AppLog, AuditLog


class Command(BaseCommand):
    help = "Elimina logs antiguos de AppLog y AuditLog según la retención indicada (en días)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Cantidad de días de retención. Ej: --days 15 conserva solo los últimos 15 días.",
        )

    def handle(self, *args, **options):
        days = options["days"]

        if days < 0:
            self.stderr.write(self.style.ERROR(
                "El parámetro --days debe ser >= 0."))
            return

        cutoff = timezone.now() - timedelta(days=days)

        # --- AppLog ---
        old_app_logs = AppLog.objects.filter(creado_en__lt=cutoff)
        count_app = old_app_logs.count()
        old_app_logs.delete()

        # --- AuditLog ---
        old_audit_logs = AuditLog.objects.filter(creado_en__lt=cutoff)
        count_audit = old_audit_logs.count()
        old_audit_logs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"✔ Limpieza completada. "
                f"AppLog eliminados: {count_app}. "
                f"AuditLog eliminados: {count_audit}. "
                f"Retención aplicada: {days} días."
            )
        )
