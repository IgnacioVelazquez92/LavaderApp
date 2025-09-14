# apps/payments/models.py
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MedioPago(models.Model):
    """
    Medio de pago configurable por cada empresa.
    Ej: 'Efectivo', 'MercadoPago', 'Transferencia BBVA', 'Transferencia Santander'.
    """

    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="medios_pago",
        help_text=_("Empresa a la que pertenece este medio de pago."),
    )
    nombre = models.CharField(
        max_length=100,
        help_text=_("Nombre visible del medio de pago.")
    )
    activo = models.BooleanField(
        default=True,
        help_text=_("Si está disponible para usar en la caja.")
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Medio de pago")
        verbose_name_plural = _("Medios de pago")
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nombre"],
                name="unique_medio_pago_por_empresa",
            ),
        ]

    def __str__(self) -> str:
        return self.nombre


class Pago(models.Model):
    """
    Representa un pago realizado sobre una Venta.

    Reglas clave:
    - El monto debe ser > 0 (validado en servicio y por CheckConstraint).
    - Los pagos de propina (es_propina=True) NO reducen el saldo de la venta.
    - Idempotencia opcional por (venta, idempotency_key) para integraciones.
    - Integridad de tenant: el Medio de pago debe pertenecer a la MISMA empresa que la Venta
      (se valida en el service y/o clean(); no se puede expresar con constraint SQL cross-table).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Identificador único del pago (UUID)."),
    )

    venta = models.ForeignKey(
        "sales.Venta",
        on_delete=models.CASCADE,
        related_name="pagos",
        help_text=_("Venta a la que se asocia este pago."),
    )

    medio = models.ForeignKey(
        "payments.MedioPago",
        on_delete=models.PROTECT,
        related_name="pagos",
        help_text=_("Medio de pago utilizado."),
    )

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=_("Monto del pago. Debe ser mayor a 0."),
    )

    es_propina = models.BooleanField(
        default=False,
        help_text=_("Si el pago corresponde a una propina."),
    )

    referencia = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Referencia externa (ID de transacción, cupón, etc.)."),
    )

    notas = models.TextField(
        blank=True,
        null=True,
        help_text=_("Notas internas relacionadas al pago."),
    )

    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=_("Clave de idempotencia para evitar pagos duplicados."),
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pagos_creados",
        help_text=_("Usuario que registró el pago."),
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pago")
        verbose_name_plural = _("Pagos")
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["creado_en"]),
            models.Index(fields=["venta", "es_propina"]),
        ]
        constraints = [
            # Idempotencia por venta (solo aplica cuando hay clave)
            models.UniqueConstraint(
                fields=["venta", "idempotency_key"],
                name="unique_pago_idempotency_per_venta",
                condition=~models.Q(idempotency_key=None),
            ),
            # Monto > 0 a nivel DB
            models.CheckConstraint(
                check=models.Q(monto__gt=0),
                name="pago_monto_gt_0",
            ),
        ]

    def __str__(self) -> str:
        medio = getattr(self.medio, "nombre", "—")
        return f"Pago {self.monto} via {medio} (Venta {self.venta_id})"

    @property
    def es_saldo(self) -> bool:
        """True si afecta el saldo (no propina)."""
        return not self.es_propina

    def monto_decimal(self) -> Decimal:
        """Devuelve el monto como Decimal."""
        return Decimal(self.monto)
