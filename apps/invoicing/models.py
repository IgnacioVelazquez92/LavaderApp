from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def invoice_upload_path(instance: "Comprobante", filename: str) -> str:
    """
    Ubicación consistente para archivos de comprobantes (HTML/PDF).
    MEDIA_ROOT/invoices/<empresa_id>/<sucursal_id>/YYYY/MM/<uuid>_<filename>
    """
    y = datetime.utcnow().strftime("%Y")
    m = datetime.utcnow().strftime("%m")
    return f"invoices/{instance.empresa_id}/{instance.sucursal_id}/{y}/{m}/{instance.id}_{filename}"


PUNTO_VENTA_VALIDATOR = RegexValidator(
    regex=r"^\d{1,4}$",
    message="El punto de venta debe ser un número de 1 a 4 dígitos (sin separadores).",
)


class TipoComprobante(models.TextChoices):
    """
    Tipos de comprobante NO fiscal contemplados en el MVP.
    Se puede extender a futuro (ej. 'RECIBO', 'NOTA', etc.).
    """
    TICKET = "TICKET", "Ticket"
    REMITO = "REMITO", "Remito"


# --------------------------------------------------------------------------------------
# Core models
# --------------------------------------------------------------------------------------

class SecuenciaComprobante(models.Model):
    """
    Mantiene el contador de numeración por (Sucursal, Tipo, Punto de Venta).
    Notas:
      - En MVP numeramos por Sucursal+Tipo; incluimos punto_venta para escenarios donde
        una misma sucursal opere múltiples puntos (ej. caja 0001, 0002).
      - El incremento DEBE realizarse en transacción/SELECT FOR UPDATE (service `numbering`).
    """
    sucursal = models.ForeignKey(
        "org.Sucursal", on_delete=models.CASCADE, related_name="secuencias_comprobantes")
    tipo = models.CharField(max_length=16, choices=TipoComprobante.choices)
    punto_venta = models.CharField(max_length=4, validators=[
                                   PUNTO_VENTA_VALIDATOR], default="1")
    proximo_numero = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)])
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoicing_secuencia"
        unique_together = (("sucursal", "tipo", "punto_venta"),)
        ordering = ("sucursal_id", "tipo", "punto_venta")

    def __str__(self) -> str:
        return f"Secuencia {self.sucursal} · {self.tipo} · PV {self.punto_venta} → {self.proximo_numero}"


class ClienteFacturacion(models.Model):
    """
    Perfil opcional de facturación (no fiscal) para asociar a un Comprobante.
    Útil cuando los datos del cliente de operación difieren de los de facturación.
    """
    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.CASCADE, related_name="perfiles_facturacion")
    cliente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.SET_NULL,
        related_name="perfiles_facturacion",
        null=True,
        blank=True,
        help_text="Relación opcional al cliente operativo; puede ser un tercero."
    )
    razon_social = models.CharField(max_length=255)
    cuit = models.CharField(max_length=20, blank=True,
                            help_text="Identificación (DNI/CUIT). No validado en MVP.")
    domicilio = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=64, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoicing_cliente_facturacion"
        ordering = ("-actualizado_en", "razon_social")
        verbose_name = "Cliente de Facturación"
        verbose_name_plural = "Clientes de Facturación"

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.cuit or 'SIN ID'})"


class Comprobante(models.Model):
    """
    Comprobante NO FISCAL emitido para una Venta 'pagada'.

    Invariantes:
      - Snapshot inmutable: `snapshot` guarda la venta al momento de emisión (ítems, totales, textos).
      - Numeración única por (Sucursal, Tipo, Punto de Venta, Número).
      - Uno-a-uno con Venta para MVP (una venta → un comprobante). Si a futuro se requiere
        admitir re-emisiones, convertir `OneToOneField` a `ForeignKey` y modelar anulaciones.

    Archivos:
      - `archivo_html` y `archivo_pdf` (opcional) se persisten en MEDIA_ROOT vía `invoice_upload_path`.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Redundancias útiles para queries multi-tenant rápidas (evita join para empresa)
    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.PROTECT, related_name="comprobantes")
    sucursal = models.ForeignKey(
        "org.Sucursal", on_delete=models.PROTECT, related_name="comprobantes")

    venta = models.OneToOneField(
        "sales.Venta",
        on_delete=models.PROTECT,
        related_name="comprobante",
        help_text="Venta asociada; en MVP es 1:1."
    )
    cliente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.PROTECT,
        related_name="comprobantes",
        help_text="Cliente operativo de la venta."
    )
    cliente_facturacion = models.ForeignKey(
        "invoicing.ClienteFacturacion",
        on_delete=models.SET_NULL,
        related_name="comprobantes",
        null=True,
        blank=True,
        help_text="Perfil de facturación alternativo (opcional)."
    )

    tipo = models.CharField(
        max_length=16, choices=TipoComprobante.choices, default=TipoComprobante.TICKET)
    punto_venta = models.CharField(max_length=4, validators=[
                                   PUNTO_VENTA_VALIDATOR], default="1")
    numero = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    moneda = models.CharField(max_length=8, default="ARS")
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Snapshot inmutable (estructura libre controlada desde `services.emit`)
    snapshot = models.JSONField(
        help_text="Copia inmutable de la venta al momento de emisión (empresa, sucursal, cliente, items, totales, textos)."
    )

    # Archivos resultantes
    archivo_html = models.FileField(
        upload_to=invoice_upload_path, blank=True, null=True)
    archivo_pdf = models.FileField(
        upload_to=invoice_upload_path, blank=True, null=True)

    # Metadatos
    emitido_en = models.DateTimeField(auto_now_add=True)
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comprobantes_emitidos"
    )

    class Meta:
        db_table = "invoicing_comprobante"
        ordering = ("-emitido_en", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("sucursal", "tipo", "punto_venta", "numero"),
                name="uq_num_comprobante_por_sucursal_tipo_pv"
            )
        ]

    # -----------------------------------------
    # Representación y utilidades de numeración
    # -----------------------------------------
    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.numero_completo}"

    @property
    def numero_completo(self) -> str:
        """
        Formato legible: 0001-00000042 (PV-numero con padding)
        """
        pv = str(self.punto_venta).zfill(4)
        n = str(self.numero).zfill(8)
        return f"{pv}-{n}"

    def get_absolute_url(self) -> str:
        return reverse("invoicing:detail", kwargs={"pk": str(self.id)})
