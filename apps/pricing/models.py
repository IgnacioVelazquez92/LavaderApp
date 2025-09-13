# apps/pricing/models.py
from __future__ import annotations

from django.db import models
from django.db.models import Q, F, CheckConstraint, UniqueConstraint
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class PrecioServicioQuerySet(models.QuerySet):
    """
    QuerySet específico para consultas de negocio sobre precios.

    Métodos clave:
      - de_empresa(empresa)
      - de_combinacion(sucursal, servicio, tipo_vehiculo)
      - vigentes_en(fecha) -> precios activos y vigentes en 'fecha' (hoy por defecto)
      - abiertos() -> precios con vigencia abierta (sin fecha de fin) y activos
    """

    def de_empresa(self, empresa):
        return self.filter(empresa=empresa)

    def de_combinacion(self, sucursal, servicio, tipo_vehiculo):
        return self.filter(
            sucursal=sucursal,
            servicio=servicio,
            tipo_vehiculo=tipo_vehiculo,
        )

    def vigentes_en(self, fecha=None):
        if fecha is None:
            fecha = timezone.localdate()
        return self.filter(
            activo=True,
            vigencia_inicio__lte=fecha
        ).filter(
            Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=fecha)
        )

    def abiertos(self):
        return self.filter(activo=True, vigencia_fin__isnull=True)


class Moneda(models.TextChoices):
    """Catálogo mínimo de monedas soportadas."""
    ARS = "ARS", "Peso argentino"
    USD = "USD", "Dólar estadounidense"  # opcional según tu operación


class PrecioServicio(models.Model):
    """
    Precio vigente de un Servicio por Tipo de Vehículo y Sucursal dentro de una Empresa.

    Reglas de negocio relevantes:
      - Multi-tenant: empresa, sucursal, servicio y tipo_vehiculo deben pertenecer a la MISMA empresa.
      - Vigencias: no debe haber solapamientos de vigencia para la misma combinación (srv×tipo×suc).
      - Único “abierto y activo” por combinación (si existe un registro con vigencia_fin NULL y activo=True,
        no puede crearse otro igual sin cerrar el anterior).
    """

    # --- Relaciones (multi-tenant) ---
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="precios"
    )
    sucursal = models.ForeignKey(
        "org.Sucursal",
        on_delete=models.CASCADE,
        related_name="precios"
    )
    servicio = models.ForeignKey(
        "catalog.Servicio",
        on_delete=models.CASCADE,
        related_name="precios"
    )
    tipo_vehiculo = models.ForeignKey(
        "vehicles.TipoVehiculo",
        on_delete=models.CASCADE,
        related_name="precios"
    )

    # --- Datos económicos ---
    precio = models.DecimalField(
        "Precio",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Monto positivo, hasta 2 decimales."
    )
    moneda = models.CharField(
        "Moneda",
        max_length=3,
        choices=Moneda.choices,
        default=Moneda.ARS
    )

    # --- Vigencia ---
    vigencia_inicio = models.DateField(
        "Vigente desde",
        help_text="Fecha de inicio de vigencia (incluida)."
    )
    vigencia_fin = models.DateField(
        "Vigente hasta",
        null=True,
        blank=True,
        help_text="Opcional. Dejar vacío para vigencia abierta."
    )

    # --- Estado y trazabilidad ---
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    # Gestor
    objects = PrecioServicioQuerySet.as_manager()

    class Meta:
        verbose_name = "Precio de servicio"
        verbose_name_plural = "Precios de servicio"

        # Índices útiles para consultas por combinación y fecha
        indexes = [
            models.Index(
                fields=["empresa", "sucursal", "servicio",
                        "tipo_vehiculo", "vigencia_inicio"],
                name="pricing_idx_comb_inicio",
            ),
            models.Index(
                fields=["empresa", "sucursal", "servicio",
                        "tipo_vehiculo", "vigencia_fin"],
                name="pricing_idx_comb_fin",
            ),
            models.Index(
                fields=["empresa", "activo", "vigencia_fin"],
                name="pricing_idx_estado",
            ),
        ]

        # Reglas en base de datos (parciales y chequeos)
        constraints = [
            # fin >= inicio (o fin es NULL)
            CheckConstraint(
                check=Q(vigencia_fin__isnull=True) | Q(
                    vigencia_fin__gte=F("vigencia_inicio")),
                name="pricing_chk_fin_ge_inicio",
            ),
            # No dos registros con la MISMA combinación y mismo inicio (orden lógico)
            UniqueConstraint(
                fields=["empresa", "sucursal", "servicio",
                        "tipo_vehiculo", "vigencia_inicio"],
                name="pricing_unq_misma_combinacion_mismo_inicio",
            ),
            # A nivel de DB, garantizamos que solo haya UNO abierto+activo por combinación
            UniqueConstraint(
                fields=["empresa", "sucursal", "servicio", "tipo_vehiculo"],
                condition=Q(vigencia_fin__isnull=True, activo=True),
                name="pricing_unq_abierto_activo_por_combinacion",
            ),
        ]

    # ------------------------------
    # Validaciones de dominio
    # ------------------------------
    def clean(self):
        """
        Validación integral:
          - Consistencia multi-tenant (todas las FKs pertenecen a 'empresa').
          - Moneda válida (catálogo).
          - No solapamiento de vigencias para la misma combinación.
        """
        from .validators import (
            validar_consistencia_empresa,
            validar_moneda,
            validar_solapamiento_vigencias,
        )

        # Consistencia de empresa en FKs
        validar_consistencia_empresa(self)

        # Moneda
        validar_moneda(self.moneda, permitidas=[c.value for c in Moneda])

        # Solapamientos (contra otros precios activos de la misma combinación)
        validar_solapamiento_vigencias(self)

    # ------------------------------
    # Helpers de negocio
    # ------------------------------
    def esta_vigente_en(self, fecha=None) -> bool:
        """True si el precio está activo y cubre 'fecha' (hoy por defecto)."""
        if fecha is None:
            fecha = timezone.localdate()
        if not self.activo:
            return False
        if self.vigencia_inicio and self.vigencia_inicio > fecha:
            return False
        if self.vigencia_fin and self.vigencia_fin < fecha:
            return False
        return True

    @property
    def periodo_str(self) -> str:
        """Representación amigable del período de vigencia."""
        fin = self.vigencia_fin.isoformat() if self.vigencia_fin else "abierto"
        return f"{self.vigencia_inicio.isoformat()} → {fin}"

    def __str__(self) -> str:
        return (
            f"{self.servicio} × {self.tipo_vehiculo} @ {self.sucursal} "
            f"— {self.moneda} {self.precio}  ({self.periodo_str})"
        )
