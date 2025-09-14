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

    - Tiene un ciclo de vida (FSM) definido en `apps/sales/fsm.py`.
    - Es la entidad madre de la que dependen:
        pagos, comprobantes, notificaciones, etc.
    - Los totales se recalculan cada vez que cambian sus ítems
      (ver calculations.py y signals.py).
    """

    ESTADOS = [
        ("borrador", "Borrador"),
        ("en_proceso", "En proceso"),
        ("terminado", "Terminado"),
        ("pagado", "Pagado"),
        ("cancelado", "Cancelado"),
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

    estado = models.CharField(
        max_length=20, choices=ESTADOS, default="borrador"
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
        ]

    def __str__(self):
        return f"Venta {self.id} - {self.cliente} ({self.get_estado_display()})"


class VentaItem(models.Model):
    """
    Ítem de una Venta.

    - Cachea el `precio_unitario` vigente al momento de agregarlo.
    - Se usa para calcular los totales de la Venta.
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
        # un servicio por venta (editable cantidad)
        unique_together = ("venta", "servicio")
        ordering = ["venta", "id"]

    def __str__(self):
        return f"{self.servicio} x {self.cantidad} (Venta {self.venta_id})"

    @property
    def subtotal(self):
        """Subtotal de este ítem (cantidad × precio_unitario)."""
        return self.cantidad * self.precio_unitario
