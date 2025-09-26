# apps/saas/models.py
"""
Modelos base del módulo SaaS (MVP escalable a pasarela de pagos).

Diseño:
- PlanSaaS: define límites “soft” y precio. Incluye bandera `default` y `trial_days`.
- SuscripcionSaaS: relación 1:1 con Empresa (MVP). Mantiene estado lógico por fechas y
  metadatos de pago para integración futura con pasarela (Mercado Pago, Stripe, etc.).

Escalabilidad prevista:
- Trial gratuito: trial_days en PlanSaaS; SuscripcionSaaS calcula trial automáticamente.
- Upgrades/cobros: campos external_* para almacenar IDs de la pasarela y payment_status.
- Renovaciones: extender `fin` según ciclo de facturación cuando haya pago confirmado.

Reglas clave:
- vigente: True si estado == "activa" y hoy ∈ [inicio, fin] (o fin es NULL).
- is_trialing: True si payment_status == "trial" y hoy <= trial_ends_at.
- One-to-one empresa↔suscripción (MVP). Futuro: histórico en tabla aparte si se requiere.

Integraciones previstas (sin implementar en este archivo):
- services/subscriptions.py: crear/renovar/cambiar plan; confirmar pagos; extender `fin`.
- webhooks/<pasarela>: actualizar payment_status/external_*; registrar eventos.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from django.db import models
from django.utils import timezone


class PlanSaaS(models.Model):
    """
    Define un plan comercial del SaaS con límites y precios.

    Campos principales:
    - default: si es el plan por defecto para nuevas empresas.
    - trial_days: cantidad de días de prueba al crear suscripciones con este plan.
    - max_*: límites “soft” (enforcement configurable fuera de este modelo).
    - precio_mensual: valor referencial; la pasarela puede tener su propio price id.
    - external_plan_id: identificador del plan en la pasarela (ej. Mercado Pago preapproval plan).

    Notas:
    - No se hace enforcement aquí; se usa apps/saas/limits.py + settings (SAAS_ENFORCE_LIMITS).
    - Si hay múltiples `default=True`, la app debe decidir cuál tomar (preferir activo y más barato).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)

    # Flags de activación y plan por defecto
    activo = models.BooleanField(default=True)
    default = models.BooleanField(
        default=False,
        help_text="Si está activo y marcado como default, se asigna a empresas nuevas."
    )

    # Trial gratuito
    trial_days = models.PositiveIntegerField(
        default=0,
        help_text="Días de prueba gratuitos al crear la suscripción (0 = sin trial)."
    )

    # Límites (soft)
    max_empresas_por_usuario = models.PositiveIntegerField(
        default=1,
        help_text="Cuántas empresas puede crear/poseer un usuario (owner)."
    )
    max_sucursales_por_empresa = models.PositiveIntegerField(default=1)
    max_usuarios_por_empresa = models.PositiveIntegerField(
        default=5,
        help_text="Membresías activas (EmpresaMembership) en la empresa."
    )
    max_empleados_por_sucursal = models.PositiveIntegerField(
        default=5,
        help_text="Membresías activas asignadas a una sucursal específica."
    )
    max_storage_mb = models.PositiveIntegerField(default=200)

    # Precio referencial (la pasarela puede tener su propio price)
    precio_mensual = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    # Integración con pasarela (opcional, para mapear planes/precios externos)
    external_plan_id = models.CharField(
        max_length=120, blank=True,
        help_text="ID del plan en la pasarela (ej. preapproval plan de Mercado Pago)."
    )

    # Auditoría
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plan SaaS"
        verbose_name_plural = "Planes SaaS"
        ordering = ["-activo", "nombre"]

    def __str__(self) -> str:
        return self.nombre

    # --- Helpers de trial ----------------------------------------------------

    def compute_trial_ends_at(self, start: date) -> Optional[date]:
        """
        Devuelve la fecha de fin de trial a partir de `start` y `trial_days`.
        Si trial_days == 0, retorna None.
        """
        if self.trial_days <= 0:
            return None
        return start + timedelta(days=self.trial_days)


class SuscripcionSaaS(models.Model):
    """
    Suscripción de una Empresa a un Plan.

    Estados funcionales (estado):
    - activa: suscripción válida/operativa.
    - vencida: alcanzó fin sin renovación.
    - suspendida: pausa manual/administrativa (no vigente aunque no haya llegado fin).

    Estados de pago (payment_status) - independientes del estado funcional:
    - trial: dentro del período de prueba.
    - paid: cobro al día (último ciclo pago confirmado).
    - unpaid: sin cobro vigente (ej. expiró trial o falló pago).
    - past_due: vencida pendiente de pago (opcional para granularidad futura).

    Notas:
    - En MVP, `vigente` se calcula con `estado` y fechas; el `payment_status` es
      informativo para UI/gestión y ganchos de pasarela.
    - Guardamos external_* para conciliación con la pasarela (ej. Mercado Pago).
    """

    ESTADOS = (
        ("activa", "Activa"),
        ("vencida", "Vencida"),
        ("suspendida", "Suspendida"),
    )

    PAYMENT_STATUSES = (
        ("trial", "Trial"),
        ("paid", "Paid"),
        ("unpaid", "Unpaid"),
        ("past_due", "Past due"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empresa = models.OneToOneField(
        "org.Empresa", on_delete=models.CASCADE, related_name="suscripcion",
        help_text="Relación 1:1 en MVP. Futuro: mover histórico a otra tabla si se requiere."
    )
    plan = models.ForeignKey(
        PlanSaaS, on_delete=models.PROTECT, related_name="suscripciones"
    )

    # Estado funcional y ventana de vigencia
    estado = models.CharField(max_length=20, choices=ESTADOS, default="activa")
    inicio = models.DateField(default=timezone.localdate)
    fin = models.DateField(null=True, blank=True)

    # Pago/pasarela (placeholders para integración real)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUSES, default="unpaid",
        help_text="trial/paid/unpaid/past_due para UI y conciliación."
    )
    external_customer_id = models.CharField(
        max_length=120, blank=True,
        help_text="ID del cliente en la pasarela (ej. Mercado Pago)."
    )
    external_subscription_id = models.CharField(
        max_length=120, blank=True,
        help_text="ID de la suscripción/adhesión en la pasarela."
    )
    external_plan_id = models.CharField(
        max_length=120, blank=True,
        help_text="Plan/code en la pasarela (útil si difiere del de PlanSaaS)."
    )
    last_payment_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)

    # Auditoría
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Suscripción SaaS"
        verbose_name_plural = "Suscripciones SaaS"
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["payment_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.empresa} → {self.plan} ({self.estado}/{self.payment_status})"

    # --- Propiedades de estado -----------------------------------------------

    @property
    def hoy(self) -> date:
        return timezone.localdate()

    @property
    def vigente(self) -> bool:
        """
        La suscripción es vigente si:
          - estado == "activa", y
          - inicio <= hoy <= fin (o fin es None).
        """
        if self.estado != "activa":
            return False
        if self.fin is None:
            return self.inicio <= self.hoy
        return self.inicio <= self.hoy <= self.fin

    @property
    def is_trialing(self) -> bool:
        """
        True si la suscripción está en status 'trial' y hoy <= trial_ends_at.
        Se calcula usando plan.trial_days e inicio de la suscripción.
        """
        if self.payment_status != "trial":
            return False
        trial_ends = self.plan.compute_trial_ends_at(self.inicio)
        return bool(trial_ends and self.hoy <= trial_ends)

    @property
    def trial_ends_at(self) -> Optional[date]:
        """
        Fecha en la que termina el trial (None si plan.trial_days == 0).
        """
        return self.plan.compute_trial_ends_at(self.inicio)

    # --- Métodos de transición (a ser llamados desde services) ----------------

    def start_trial(self) -> None:
        """
        Inicializa la suscripción como trial (si el plan tiene trial_days > 0).
        No guarda automáticamente: los services deberían persistir y loguear.
        """
        if self.plan.trial_days > 0:
            self.payment_status = "trial"
            # `fin` durante trial puede quedar en None y usarse trial_ends_at solo para UI,
            # o bien setear fin = trial_ends_at para que 'vigente' coincida con el trial.
            # MVP: dejamos fin como esté; la vigencia funcional depende de estado/fechas.
        else:
            self.payment_status = "unpaid"

    def mark_paid_cycle(self, months: int = 1) -> None:
        """
        Marca un ciclo pago confirmado y extiende la ventana de vigencia.
        - Actualiza payment_status="paid", last_payment_at, next_billing_at.
        - Extiende `fin` en `months` meses (lógica simple para MVP).
        Nota: la extensión exacta del período puede ajustarse a reglas de la pasarela.
        """
        now = timezone.now()
        self.payment_status = "paid"
        self.last_payment_at = now
        # Siguiente cobro aproximado (MVP: +30 días × months). Ajustar a calendario si se requiere.
        delta_days = 30 * max(1, months)
        self.next_billing_at = now + timezone.timedelta(days=delta_days)

        # Extender vigencia funcional
        today = self.hoy
        base = self.fin if self.fin and self.fin >= today else today
        self.fin = base + timedelta(days=delta_days)

    def mark_unpaid(self) -> None:
        """
        Coloca la suscripción como 'unpaid' (por ejemplo, al finalizar trial sin pago).
        No cambia 'estado'; eso lo decide la política (p.ej., pasar a 'vencida').
        """
        self.payment_status = "unpaid"

    def mark_suspended(self) -> None:
        """
        Suspende funcionalmente la suscripción (no vigente aunque esté dentro de fechas).
        """
        self.estado = "suspendida"

    def mark_active(self) -> None:
        """
        Reactiva funcionalmente la suscripción (siempre que las fechas acompañen).
        """
        self.estado = "activa"

    def mark_expired_if_needed(self) -> None:
        """
        Si hoy > fin y estado no es 'suspendida', colocar 'vencida'.
        Útil para cron/management command o check puntual en services.
        """
        if self.estado == "suspendida":
            return
        if self.fin and self.hoy > self.fin:
            self.estado = "vencida"
