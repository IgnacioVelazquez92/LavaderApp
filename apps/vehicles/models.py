from django.db import models
from django.db.models import Q
from django.utils import timezone

# Referencias cruzadas
# - Empresa: apps.org.models.Empresa
# - Cliente: apps.customers.models.Cliente


def _normalizar_patente(patente: str) -> str:
    """
    Normaliza formato de patente:
    - Quita espacios y guiones
    - Convierte a mayúsculas
    """
    if not patente:
        return patente
    return patente.replace("-", "").replace(" ", "").upper()


class TipoVehiculo(models.Model):
    """
    Catálogo simple de tipos: auto, moto, camioneta, utilitario, etc.
    Escalable para que la empresa pueda crear propios (opcional).
    """
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="tipos_vehiculo",
        help_text="El tipo pertenece a la empresa (multi-tenant).",
    )
    nombre = models.CharField(max_length=50)
    slug = models.SlugField(max_length=60)
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(default=timezone.now, editable=False)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("empresa", "slug"),)
        indexes = [
            models.Index(fields=["empresa", "slug"]),
            models.Index(fields=["empresa", "activo"]),
        ]
        ordering = ["nombre"]
        verbose_name = "Tipo de vehículo"
        verbose_name_plural = "Tipos de vehículo"

    def __str__(self):
        return f"{self.nombre}"


class Vehiculo(models.Model):
    """
    Vehículo de un cliente. La unicidad de patente es por empresa (tenant).
    Se contempla soft delete mediante 'activo'.
    """
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="vehiculos",
    )
    cliente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.PROTECT,
        related_name="vehiculos",
        help_text="Propietario del vehículo.",
    )
    tipo = models.ForeignKey(
        "vehicles.TipoVehiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehiculos",
    )

    marca = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    anio = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=40, blank=True)

    # Patente normalizada (sin guiones/espacios, mayúsculas)
    patente = models.CharField(
        max_length=10, help_text="Ej.: ABC123 o AB123CD")

    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(default=timezone.now, editable=False)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Unicidad de patente por empresa considerando solo activos (soft delete aware)
            models.UniqueConstraint(
                fields=["empresa", "patente"],
                condition=Q(activo=True),
                name="uniq_patente_por_empresa_activos",
            )
        ]
        indexes = [
            models.Index(fields=["empresa", "patente"]),
            models.Index(fields=["empresa", "cliente"]),
            models.Index(fields=["activo"]),
        ]
        ordering = ["-actualizado", "patente"]
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"

    def clean(self):
        # Normalizar patente en clean para que el validador/DB vean el valor ya transformado
        self.patente = _normalizar_patente(self.patente)

    def save(self, *args, **kwargs):
        # Doble seguridad de normalización
        self.patente = _normalizar_patente(self.patente)
        super().save(*args, **kwargs)

    def __str__(self):
        base = self.patente or "SIN_PATENTE"
        detalle = " ".join(filter(None, [self.marca, self.modelo]))
        return f"{base} — {detalle}".strip(" —")
