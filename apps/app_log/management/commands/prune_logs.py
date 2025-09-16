# apps/app_log/management/commands/prune_logs.py
"""
Comando de gestión para purgar logs antiguos y controlar retención.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.app_log.models import AppLog, AuditLog


class Command(BaseCommand):
    help = "Purge old logs by kind and retention days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=["app", "audit", "all"],
            default="all",
            help="Tipo de log a purgar",
        )
        parser.add_argument(
            "--days",
            type=int,
            required=True,
            help="Cantidad de días a conservar",
        )

    def handle(self, *args, **opts):
        days = opts["days"]
        cutoff = timezone.now() - timedelta(days=days)
        kind = opts["kind"]
        total = 0

        if kind in ("app", "all"):
            n = AppLog.objects.filter(creado_en__lt=cutoff).delete()[0]
            self.stdout.write(self.style.SUCCESS(f"AppLog purged: {n}"))
            total += n

        if kind in ("audit", "all"):
            n = AuditLog.objects.filter(creado_en__lt=cutoff).delete()[0]
            self.stdout.write(self.style.SUCCESS(f"AuditLog purged: {n}"))
            total += n

        self.stdout.write(self.style.SUCCESS(f"Total purged: {total}"))
