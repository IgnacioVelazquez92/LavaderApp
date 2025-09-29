# apps/sales/models.py
import uuid
from django.db import models
from django.conf import settings

from apps.org.models import Empresa, Sucursal
from apps.customers.models import Cliente
from apps.vehicles.models import Vehiculo
from apps.catalog.models import Servicio


class Venta(models.Model):
    """
    Representa una orden de servicio / venta.

    - Ciclo operativo (FSM) en `apps/sales/fsm.py`: controla SOLO el proceso del trabajo.
      Estados: borrador | en_proceso | terminado | cancelado.
    - Estado de pago separado en `payment_status`: no_pagada | parcial | pagada.
    - Entidad madre: pagos, comprobantes, notificaciones, etc.
    - Totales se recalculan cuando cambian los ítems (ver calculations.py y signals.py).
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
        Empresa, on_delete=models.CASCADE, related_name="ventas"
    )
    sucursal = models.ForeignKey(
        Sucursal, on_delete=models.PROTECT, related_name="ventas"
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="ventas"
    )
    vehiculo = models.ForeignKey(
        Vehiculo, on_delete=models.PROTECT, related_name="ventas"
    )

    # Estado operativo (proceso)
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default="borrador")

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
