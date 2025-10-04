# apps/notifications/models.py
"""
Modelos de notificaciones (plantillas y log de envíos) para LavaderosApp.

Objetivo del módulo:
- Gestionar plantillas parametrizables por empresa y canal (email/whatsapp).
- Renderizar y registrar cada intento de envío (simulado en MVP) con su estado.
- Asegurar multi-tenant (FK a Empresa) y trazabilidad mínima.

Decisiones:
- Estados habilitantes para enviar: SOLO cuando la venta está "terminado" (regla de negocio
  aplicada en services/dispatcher.py; acá solo persistimos).
- Canal soportado en MVP: email/whatsapp (extensible).
- Idempotencia: no obligatoria en MVP; se deja un campo opcional `idempotency_key` para futuro.
- Tenancy: todas las entidades referencian Empresa; Log guarda además Venta para trazabilidad.
- Campos *_tpl son "plantilla" (antes de render); *_renderizado son el resultado final del render.

Notas:
- El validador de formato del destinatario depende del canal (email vs. E.164). Se recomienda
  implementarlo en el service/dispatcher antes de crear el Log (fail-fast). En el modelo
  mantenemos validaciones simples de longitud y no-nulos cuando corresponda.
"""

from __future__ import annotations
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Canal(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"
    # Futuro: SMS = "sms", "SMS"


class EstadoEnvio(models.TextChoices):
    ENVIADO = "enviado", "Enviado"
    ERROR = "error", "Error"
    # Futuro: PENDIENTE = "pendiente", "Pendiente" (si se usa cola asíncrona real)


class PlantillaNotif(models.Model):
    """
    Plantilla parametrizable por empresa y canal.

    - clave: identificador único por empresa (ej. "ready_to_pickup_email").
    - canal: email o whatsapp (MVP).
    - asunto_tpl: solo aplica a email (opcional). Para WhatsApp suele no usarse.
    - cuerpo_tpl: cuerpo con variables {{...}}; el renderer las completará.
    - activo: para habilitar/deshabilitar sin borrar.

    Unicidad:
      - (empresa, clave) es única → permite referenciar por clave en UI/servicios.

    Indexación:
      - índices por empresa/activo/canal para listados y búsquedas comunes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="plantillas_notif",
    )
    clave = models.SlugField(
        max_length=80,
        help_text="Identificador único por empresa (ej: ready_to_pickup_email).",
    )
    canal = models.CharField(max_length=16, choices=Canal.choices)
    asunto_tpl = models.CharField(
        max_length=200,
        blank=True,
        help_text="Solo para email. Puede dejarse vacío.",
    )
    cuerpo_tpl = models.TextField(
        help_text="Texto de la notificación con variables {{...}} (ej. {{cliente.nombre}})."
    )
    activo = models.BooleanField(default=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_notif_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_plantilla"
        verbose_name = "Plantilla de notificación"
        verbose_name_plural = "Plantillas de notificación"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "clave"], name="uq_notifications_plantilla_empresa_clave"
            ),
            models.CheckConstraint(
                check=~models.Q(cuerpo_tpl=""),
                name="ck_notifications_plantilla_cuerpo_no_vacio",
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "activo"],
                         name="idx_notif_tpl_emp_activo"),
            models.Index(fields=["empresa", "canal"],
                         name="idx_notif_tpl_emp_canal"),
            models.Index(fields=["creado_en"], name="idx_notif_tpl_creado"),
        ]
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"[{self.empresa_id}] {self.clave} ({self.get_canal_display()})"

    # Helpers opcionales
    @property
    def es_email(self) -> bool:
        return self.canal == Canal.EMAIL

    @property
    def es_whatsapp(self) -> bool:
        return self.canal == Canal.WHATSAPP


class LogNotif(models.Model):
    """
    Registro histórico de envíos (o intentos) de notificaciones.

    - empresa: para particionado lógico multi-tenant (redundamos con venta.empresa por performance).
    - venta: para trazabilidad (qué servicio/trabajo se notificó).
    - plantilla: referencia opcional a la plantilla usada (si existía al momento de enviar).
    - canal: email/whatsapp.
    - destinatario: email o teléfono E.164 según canal.
    - asunto_renderizado: solo si canal=email y se usó asunto en plantilla.
    - cuerpo_renderizado: mensaje final después del render.
    - estado: enviado / error.
    - error_msg: texto técnico legible por operador (si hubo error).
    - enviado_en: timestamp del evento (set por default=timezone.now al crear).
    - idempotency_key: opcional, para deduplicar si en el futuro se desea.
    - meta: JSON libre para auditoría/diagnóstico (ej. nota_extra, contexto parcial).

    Indexación:
      - por empresa+enviado_en, por venta, y por (empresa, canal).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="logs_notif",
    )
    venta = models.ForeignKey(
        "sales.Venta",
        on_delete=models.CASCADE,
        related_name="logs_notif",
    )
    plantilla = models.ForeignKey(
        "notifications.PlantillaNotif",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )

    canal = models.CharField(max_length=16, choices=Canal.choices)
    destinatario = models.CharField(max_length=255)
    asunto_renderizado = models.CharField(max_length=200, blank=True)
    cuerpo_renderizado = models.TextField()

    estado = models.CharField(max_length=16, choices=EstadoEnvio.choices)
    error_msg = models.TextField(blank=True, default="")
    enviado_en = models.DateTimeField(default=timezone.now)

    idempotency_key = models.CharField(
        max_length=80,
        blank=True,
        help_text="Clave opcional para deduplicar envíos (no obligatorio en MVP).",
    )
    meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Datos adicionales del envío (nota_extra, variables, etc.).",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_notif_creados",
        help_text="Usuario que ejecutó el envío (si aplica).",
    )

    class Meta:
        db_table = "notifications_log"
        verbose_name = "Log de notificación"
        verbose_name_plural = "Logs de notificaciones"
        indexes = [
            models.Index(fields=["empresa", "enviado_en"],
                         name="idx_notif_log_emp_fecha"),
            models.Index(fields=["venta", "enviado_en"],
                         name="idx_notif_log_venta_fecha"),
            models.Index(fields=["empresa", "canal"],
                         name="idx_notif_log_emp_canal"),
            models.Index(fields=["idempotency_key"],
                         name="idx_notif_log_idem"),
        ]
        ordering = ["-enviado_en"]

    def __str__(self) -> str:
        return f"[{self.empresa_id}] {self.get_canal_display()} → {self.destinatario} ({self.estado})"

    # Conveniencias
    @property
    def ok(self) -> bool:
        return self.estado == EstadoEnvio.ENVIADO

    @property
    def fallo(self) -> bool:
        return self.estado == EstadoEnvio.ERROR


class EmailServer(models.Model):
    """
    Configuración SMTP por Empresa (multi-tenant).
    Si hubiera necesidad, en el futuro se puede extender con un FK a Usuario para override granular.
    """
    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.CASCADE, related_name="email_servers"
    )
    nombre = models.CharField(max_length=120, help_text=_(
        "Alias visible, p. ej. 'Cuenta Gmail Administración'"))

    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(
        default=587, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    use_tls = models.BooleanField(
        default=True, help_text=_("STARTTLS (común en 587)"))
    use_ssl = models.BooleanField(
        default=False, help_text=_("SSL implícito (común en 465)"))

    username = models.CharField(max_length=255, blank=True, default="")
    # Guardamos la contraseña ofuscada/encriptada. Ver utils más abajo.
    password_encrypted = models.BinaryField(
        blank=True, null=True, editable=False)

    remitente_por_defecto = models.CharField(
        max_length=255, blank=True, default="", help_text=_("Ej: 'Mi Empresa <info@dominio.com>'")
    )

    activo = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "nombre")]
        verbose_name = _("Servidor de Email (SMTP)")
        verbose_name_plural = _("Servidores de Email (SMTP)")

    def __str__(self):
        return f"{self.empresa_id} • {self.nombre} ({self.host}:{self.port})"

    # Helpers de password
    def set_password(self, raw: str | None):
        from .utils.crypto import encrypt_bytes
        if raw:
            self.password_encrypted = encrypt_bytes(raw.encode("utf-8"))
        else:
            self.password_encrypted = None

    def get_password(self) -> str | None:
        from .utils.crypto import decrypt_bytes
        if not self.password_encrypted:
            return None
        try:
            return decrypt_bytes(self.password_encrypted).decode("utf-8")
        except Exception:
            return None
