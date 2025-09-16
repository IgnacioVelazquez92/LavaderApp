# apps/app_log/models.py
"""
Modelos de Observabilidad Profesional:
- AppLog: logs técnicos y de acceso HTTP (request/response, tiempos, status, IP, etc.)
- AuditLog: auditoría de negocio (CRUD) con difs before/after y contexto (usuario, IP, request_id)

Diseño:
- Campos clave indexados para consultas típicas (fecha, nivel, status, path, recurso).
- Campos *id* de usuario/empresa como CharField para ser agnósticos (UUID/int/str) y evitar FK duras.
- request_id/correlation_id permiten correlacionar AppLog ↔ AuditLog ↔ reverse proxy ↔ WSGI.
- JSONFields para meta y snapshots, cuidando sanitización desde servicios/middleware.
- Orden por fecha descendente para ver lo último primero en admin/listados.

Ejemplos de consultas:
- Últimos errores 5xx: AppLog.objects.filter(http_status__gte=500).order_by("-creado_en")
- Tráfico por endpoint: AppLog.objects.filter(http_path__icontains="/ventas/")[:500]
- ¿Quién borró la venta X?: AuditLog.objects.filter(resource_type="sales.Venta", resource_id=str(venta_id), action=AuditLog.Action.DELETE)
"""

from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


class AppLog(models.Model):
    """
    Log técnico + access log HTTP.

    Registra:
    - Contexto de request (método, path, status, duración, IP, UA).
    - Nivel y origen (logger/module) y un evento corto.
    - Identidades opcionales (empresa, usuario) sin FK rígidas.
    - request_id para correlación con otros sistemas y con AuditLog.

    Buenas prácticas:
    - No guardar secretos/tokens en meta_json (sanitizar en servicios).
    - Limitar tamaño de payloads (hacer "preview" en middleware/servicios).
    """

    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    # Identidades (agnósticas a tipo: UUID/int/str)
    empresa_id = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, help_text="ID de la empresa (tenant) en texto."
    )
    user_id = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, help_text="ID del usuario autenticado (si aplica)."
    )
    username = models.CharField(
        max_length=150, null=True, blank=True, db_index=True, help_text="Username del usuario (si aplica)."
    )

    # Correlación (permiten cruzar con AuditLog/infra)
    request_id = models.CharField(
        max_length=36, null=True, blank=True, db_index=True, help_text="X-Request-ID (UUID string)."
    )
    correlation_id = models.CharField(
        max_length=36, null=True, blank=True, db_index=True, help_text="ID de correlación transversal (opcional)."
    )

    # Taxonomía del evento
    nivel = models.CharField(
        max_length=10, choices=Level.choices, db_index=True)
    origen = models.CharField(
        max_length=120, db_index=True, help_text='Logger/módulo: ej. "http", "payments.services", "django.request".'
    )
    evento = models.CharField(
        max_length=80, db_index=True, help_text='Etiqueta corta: ej. "access_log", "unhandled_exception", "django_log".'
    )
    mensaje = models.TextField(
        help_text="Mensaje breve/útil para lectura humana.")

    # Campos HTTP frecuentes (para filtrar/ordenar rápido)
    http_method = models.CharField(
        max_length=8, null=True, blank=True, db_index=True)
    http_path = models.CharField(
        max_length=512, null=True, blank=True, db_index=True)
    http_status = models.PositiveIntegerField(
        null=True, blank=True, db_index=True)
    duration_ms = models.PositiveIntegerField(
        null=True, blank=True, db_index=True, help_text="Duración del request (ms)."
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    # Datos extendidos y estructurados del evento
    meta_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "app_log"
        verbose_name = "Log de aplicación"
        verbose_name_plural = "Logs de aplicación"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["-creado_en", "nivel", "http_status"]),
            models.Index(fields=["empresa_id", "origen", "evento"]),
            models.Index(fields=["request_id"]),
            models.Index(fields=["http_path"]),
        ]

    def __str__(self) -> str:
        return f"[{self.nivel}] {self.origen} · {self.evento}"


class AuditLog(models.Model):
    """
    Auditoría de negocio (CRUD + autenticación).

    Registra:
    - Quién (user_id/username/IP/UA), cuándo, en qué empresa.
    - Qué recurso (resource_type/resource_id) y qué acción.
    - Si fue exitoso y el motivo (opcional).
    - Cambios de campos (before/after) y snapshots previos/posteriores.

    Uso típico:
    - Señales de Django (pre_save/post_save/post_delete) o servicios explícitos.
    - Permite responder "quién borró/actualizó X y cuándo", con detalle.

    Notas:
    - Operaciones bulk_* no disparan señales → auditar desde servicios.
    - No almacenar PII innecesaria en snapshots/cambios (cumplimiento).
    """

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"           # hard delete
        SOFT_DELETE = "soft_delete", "Soft Delete"
        RESTORE = "restore", "Restore"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    # Identidades (agnósticas a tipo)
    empresa_id = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, help_text="ID de la empresa (tenant) en texto."
    )
    user_id = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, help_text="ID del usuario que ejecuta la acción."
    )
    username = models.CharField(
        max_length=150, null=True, blank=True, db_index=True, help_text="Username del usuario (si aplica)."
    )

    # Contexto de request
    request_id = models.CharField(
        max_length=36, null=True, blank=True, db_index=True, help_text="X-Request-ID para correlación."
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    # Recurso afectado
    resource_type = models.CharField(
        max_length=120, db_index=True, help_text='Etiqueta "<app_label>.<ModelName>": ej. "sales.Venta".'
    )
    resource_id = models.CharField(
        max_length=120, db_index=True, help_text="ID del recurso afectado (UUID/int/str)."
    )

    # Acción ejecutada y resultado
    action = models.CharField(
        max_length=20, choices=Action.choices, db_index=True)
    success = models.BooleanField(default=True, db_index=True)
    reason = models.TextField(
        null=True, blank=True, help_text="Motivo/justificación del cambio (opcional).")

    # Cambios y snapshots
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text='Diferencias por campo: {"campo": {"before": ..., "after": ...}}.'
    )
    snapshot_before = models.JSONField(
        default=dict, blank=True, help_text="Estado previo serializado.")
    snapshot_after = models.JSONField(
        default=dict, blank=True, help_text="Estado posterior serializado.")

    class Meta:
        db_table = "audit_log"
        verbose_name = "Auditoría de negocio"
        verbose_name_plural = "Auditorías de negocio"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["-creado_en", "empresa_id"]),
            models.Index(
                fields=["resource_type", "resource_id", "-creado_en"]),
            models.Index(fields=["action", "-creado_en"]),
        ]

    def __str__(self) -> str:
        return f"[{self.action}] {self.resource_type}:{self.resource_id}"
