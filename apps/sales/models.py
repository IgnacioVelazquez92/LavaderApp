# apps/sales/models.py
from django.db.models import Q
from django.utils import timezone
import uuid
from django.db import models
from django.conf import settings

from apps.org.models import Empresa, Sucursal
from apps.customers.models import Cliente
from apps.vehicles.models import Vehiculo
from apps.catalog.models import Servicio
from django.db.models import Q, UniqueConstraint


class Venta(models.Model):
    """
    Representa una orden de servicio / venta.

    - Ciclo operativo (FSM) en `apps/sales/fsm.py`: controla SOLO el proceso del trabajo.
      Estados: borrador | en_proceso | terminado | cancelado.
    - Estado de pago separado en `payment_status`: no_pagada | parcial | pagada.
    - Entidad madre: pagos, comprobantes, notificaciones, etc.
    - Totales se recalculan cuando cambian los ítems (ver calculations.py y signals.py).
    - Turno operativo: al crear, se asigna el turno abierto de la sucursal (cashbox.TurnoCaja).
    """

    # Estados del PROCESO (no confundir con pago)
    ESTADOS = [
        ("borrador", "Borrador"),
        ("en_proceso", "En proceso"),
        ("terminado", "Terminado"),
        ("cancelado", "Cancelado"),
    ]

    # Estados del PAGO (independientes del proceso)
    PAYMENT_STATUS = [
        ("no_pagada", "No pagada"),
        ("parcial", "Pago parcial"),
        ("pagada", "Pagada"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.CASCADE, related_name="ventas"
    )
    sucursal = models.ForeignKey(
        "org.Sucursal", on_delete=models.PROTECT, related_name="ventas"
    )
    cliente = models.ForeignKey(
        "customers.Cliente", on_delete=models.PROTECT, related_name="ventas"
    )
    vehiculo = models.ForeignKey(
        "vehicles.Vehiculo", on_delete=models.PROTECT, related_name="ventas"
    )

    # Turno operativo (asignado al crear la venta si hay turno abierto)
    turno = models.ForeignKey(
        "cashbox.TurnoCaja",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas",
        help_text="Turno operativo asignado al crear la venta.",
    )

    # Estado operativo (proceso)
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default="borrador", db_index=True)

    # Estado de pago (nuevo, reemplaza el uso de 'pagado' en estado)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default="no_pagada", db_index=True
    )

    # Totales cacheados (se recalculan con calculations.py)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    propina = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)

    notas = models.TextField(blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ventas_creadas",
    )

    class Meta:
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["empresa", "sucursal", "estado"]),
            models.Index(fields=["cliente"]),
            models.Index(fields=["payment_status"]),  # consultas por pago
            # consultas/conciliación por turno
            models.Index(fields=["turno"]),
        ]

    def __str__(self):
        return f"Venta {self.id} - {self.cliente} ({self.get_estado_display()} / {self.get_payment_status_display()})"


class VentaItem(models.Model):
    """
    Ítem de una Venta.

    - Cachea el `precio_unitario` vigente al momento de agregarlo.
    - Se usa para calcular los totales de la Venta.
    - La cantidad es editable (una fila por servicio en la venta).
    """

    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE, related_name="items"
    )
    servicio = models.ForeignKey(
        Servicio, on_delete=models.PROTECT, related_name="venta_items"
    )
    cantidad = models.PositiveIntegerField(default=1)

    # Precio unitario cacheado desde `apps.pricing.services.resolver`
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        # un servicio por venta (cantidad editable)
        unique_together = ("venta", "servicio")
        ordering = ["venta", "id"]

    def __str__(self):
        return f"{self.servicio} x {self.cantidad} (Venta {self.venta_id})"

    @property
    def subtotal(self):
        """Subtotal de este ítem (cantidad × precio_unitario)."""
        return self.cantidad * self.precio_unitario


# Promociones y ajustes
class Promotion(models.Model):
    SCOPE_ORDER = "order"
    SCOPE_ITEM = "item"
    SCOPE_CHOICES = [(SCOPE_ORDER, "Por venta"), (SCOPE_ITEM, "Por ítem")]

    MODE_PERCENT = "percent"
    MODE_AMOUNT = "amount"
    MODE_CHOICES = [(MODE_PERCENT, "%"), (MODE_AMOUNT, "Monto")]

    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.CASCADE, related_name="promotions")
    sucursal = models.ForeignKey(
        "org.Sucursal", on_delete=models.CASCADE, null=True, blank=True, related_name="promotions")
    nombre = models.CharField(max_length=120)
    codigo = models.CharField(max_length=50, blank=True, default="")
    activo = models.BooleanField(default=True)
    valido_desde = models.DateField(null=True, blank=True)
    valido_hasta = models.DateField(null=True, blank=True)
    min_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    scope = models.CharField(
        max_length=10, choices=SCOPE_CHOICES, default=SCOPE_ORDER)
    mode = models.CharField(
        max_length=10, choices=MODE_CHOICES, default=MODE_PERCENT)
    value = models.DecimalField(
        max_digits=10, decimal_places=2)  # % 0..100 o monto
    stackable = models.BooleanField(default=True)  # puede acumularse con otras
    prioridad = models.PositiveSmallIntegerField(default=10)

    # (Opcional) condición simple por método de pago
    # ej: "cash", "debit", etc.
    payment_method_code = models.CharField(
        max_length=40, blank=True, default="")

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "sucursal", "activo"]),
        ]

    def esta_vigente(self, fecha=None):
        fecha = fecha or timezone.localdate()
        if not self.activo:
            return False
        if self.valido_desde and fecha < self.valido_desde:
            return False
        if self.valido_hasta and fecha > self.valido_hasta:
            return False
        return True


class SalesAdjustment(models.Model):
    KIND_ORDER = "order"
    KIND_ITEM = "item"
    KIND_CHOICES = [(KIND_ORDER, "Venta"), (KIND_ITEM, "Ítem")]

    MODE_PERCENT = "percent"
    MODE_AMOUNT = "amount"
    MODE_CHOICES = [(MODE_PERCENT, "%"), (MODE_AMOUNT, "Monto")]

    SOURCE_MANUAL = "manual"
    SOURCE_PROMO = "promo"
    SOURCE_PAYMENT = "payment"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_PROMO, "Promoción"),
        (SOURCE_PAYMENT, "Método de pago"),
    ]

    venta = models.ForeignKey(
        "sales.Venta",
        on_delete=models.CASCADE,
        related_name="adjustments",
    )
    item = models.ForeignKey(
        "sales.VentaItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="adjustments",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    value = models.DecimalField(
        max_digits=10, decimal_places=2)  # % 0..100 o monto ≥ 0
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL
    )
    promotion = models.ForeignKey(
        "sales.Promotion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_adjustments",
    )
    motivo = models.CharField(max_length=160, blank=True, default="")
    aplicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["venta", "kind"]),
            # (no es único) ayuda a búsquedas por promo
            models.Index(fields=["venta", "promotion"]),
        ]
        constraints = [
            # ── Promos por VENTA (item IS NULL): única por (venta, promotion)
            models.UniqueConstraint(
                fields=["venta", "promotion"],
                condition=Q(promotion__isnull=False, item__isnull=True),
                name="uq_salesadj_unique_promo_order",
            ),
            # ── Promos por ÍTEM (item NOT NULL): única por (venta, item, promotion)
            models.UniqueConstraint(
                fields=["venta", "item", "promotion"],
                condition=Q(promotion__isnull=False, item__isnull=False),
                name="uq_salesadj_unique_promo_item",
            ),
            # Coherencia de kind ↔ item NULL/NOT NULL
            models.CheckConstraint(
                check=(
                    (Q(kind="order") & Q(item__isnull=True)) |
                    (Q(kind="item") & Q(item__isnull=False))
                ),
                name="ck_salesadj_kind_item_consistency",
            ),
            # Rango de value según mode
            models.CheckConstraint(
                check=(
                    (Q(mode="percent") & Q(value__gte=0) & Q(value__lte=100)) |
                    (Q(mode="amount") & Q(value__gte=0))
                ),
                name="ck_salesadj_value_range_by_mode",
            ),
        ]

    def __str__(self):
        base = f"{self.get_kind_display()} {self.get_mode_display()} {self.value}"
        if self.promotion_id:
            base += f" · {self.promotion.nombre}"
        return base
