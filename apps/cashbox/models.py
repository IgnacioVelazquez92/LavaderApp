# apps/cashbox/models.py
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
from django.utils import timezone


class CierreCaja(models.Model):
    """
    Representa un *cierre operativo de caja* para una sucursal dentro de una empresa.

    Reglas y decisiones:
    - **Solo UNA caja ABIERTA por sucursal** a la vez (UniqueConstraint parcial sobre `cerrado_en IS NULL`).
    - **Timestamps automáticos**: `abierto_en` se asigna con `timezone.now()` por defecto;
      `cerrado_en` siempre lo setea la acción de cierre (servicio), nunca el operador manualmente.
    - **Tenancy seguro**: validamos que `sucursal.empresa == empresa` en `clean()`.
    - **Trazabilidad**: `usuario` (quien abrió) y `cerrado_por` (quien cerró, opcional). `notas` captura diferencias/comentarios.
    - **Consultas**: mantenemos `empresa` como FK redundante para filtros eficientes por tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Tenancy
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.PROTECT,
        related_name="cierres_caja",
        help_text="Empresa a la que pertenece el cierre.",
    )
    sucursal = models.ForeignKey(
        "org.Sucursal",
        on_delete=models.PROTECT,
        related_name="cierres_caja",
        help_text="Sucursal donde se realizó el cierre.",
    )

    # Operativa
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cierres_abiertos",
        help_text="Usuario que abrió el cierre (cajero/operador).",
    )
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cierres_cerrados",
        null=True,
        blank=True,
        help_text="Usuario que cerró el cierre (si corresponde).",
    )

    # Tiempos (sin input manual)
    abierto_en = models.DateTimeField(
        default=timezone.now,  # apertura automática si no se especifica en servicio
        help_text="Fecha/hora de apertura del cierre.",
    )
    cerrado_en = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha/hora de cierre. Vacío mientras el cierre está abierto.",
    )

    notas = models.TextField(
        blank=True,
        help_text="Notas operativas del cierre (diferencias, observaciones, etc.).",
    )

    # Timestamps de auditoría
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cierre de Caja"
        verbose_name_plural = "Cierres de Caja"
        ordering = ("-abierto_en", "-creado_en")
        indexes = [
            models.Index(fields=("empresa", "sucursal", "abierto_en")),
            models.Index(fields=("empresa", "abierto_en")),
        ]
        constraints = [
            # Un único cierre ABIERTO por sucursal (cerrado_en IS NULL)
            models.UniqueConstraint(
                fields=("sucursal",),
                condition=Q(cerrado_en__isnull=True),
                name="uniq_cierre_abierto_por_sucursal",
            ),
            # Si está cerrado, debe cerrar en o después de abrir
            models.CheckConstraint(
                check=Q(cerrado_en__isnull=True) | Q(
                    cerrado_en__gte=F("abierto_en")),
                name="ck_cierre_cerrado_en_ge_abierto_en",
            ),
            # Defensa extra: empresa y sucursal obligatorias
            models.CheckConstraint(
                check=Q(empresa__isnull=False) & Q(sucursal__isnull=False),
                name="ck_cierre_empresa_sucursal_not_null",
            ),
        ]

    # --------- Validaciones y helpers ---------

    def clean(self):
        # Coherencia tenant: la sucursal debe pertenecer a la misma empresa
        if self.sucursal_id and self.empresa_id:
            # Para evitar query adicional si no hay cambios
            if getattr(self.sucursal, "empresa_id", None) and self.sucursal.empresa_id != self.empresa_id:
                raise ValidationError(
                    "La sucursal no pertenece a la empresa del cierre.")

    @property
    def esta_abierta(self) -> bool:
        """True si el cierre aún no fue cerrado."""
        return self.cerrado_en is None

    def rango(self) -> tuple:
        """
        Retorna el rango temporal del cierre.
        - Si está abierto: (abierto_en, None) → el servicio usará now() al calcular.
        - Si está cerrado: (abierto_en, cerrado_en).
        """
        return (self.abierto_en, self.cerrado_en)

    def __str__(self) -> str:
        estado = "abierto" if self.esta_abierta else "cerrado"
        return f"CierreCaja[suc={self.sucursal_id}] {self.abierto_en:%Y-%m-%d %H:%M} ({estado})"


class CierreCajaTotal(models.Model):
    """
    Totales por método de pago para un cierre de caja.

    - `monto`: total cobrado (NO incluye propinas).
    - `propinas`: total de propinas (se reporta separado).
    - La fila no es única globalmente: el método se repite en distintos cierres.
      Dentro de un mismo cierre, se espera 1 fila por medio (lo garantiza el service).
    """

    id = models.BigAutoField(primary_key=True)

    cierre = models.ForeignKey(
        "cashbox.CierreCaja",
        on_delete=models.CASCADE,
        related_name="totales",
        help_text="Cierre de caja asociado.",
    )
    medio = models.ForeignKey(
        "payments.MedioPago",
        on_delete=models.PROTECT,
        related_name="totales_cierre",
        help_text="Método de pago.",
    )

    monto = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    propinas = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # timestamps (ahora sí existen en DB al migrar)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Total por Método"
        verbose_name_plural = "Totales por Método"
        ordering = ("-creado_en",)  # seguro: existe el campo en la tabla
        indexes = [
            models.Index(fields=("cierre", "medio")),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(monto__gte=Decimal("0.00")) & Q(
                    propinas__gte=Decimal("0.00")),
                name="ck_totales_no_negativos",
            ),
        ]

    @property
    def total_incl_propina(self) -> Decimal:
        return (self.monto or Decimal("0.00")) + (self.propinas or Decimal("0.00"))

    def __str__(self) -> str:
        medio = getattr(self.medio, "nombre", self.medio_id)
        return f"Totales[{self.cierre_id} / {medio}]"
