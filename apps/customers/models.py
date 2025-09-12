# apps/customers/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, List

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, EmailValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


# ======================================================================================
# Utilidades de validación de CUIT (AR)
# ======================================================================================

def validar_cuit(value: str) -> None:
    """
    Valida CUIT argentino (formato solo dígitos, 11 caracteres, dígito verificador).
    No normaliza (eso debería hacerlo la capa de normalizers/services antes de guardar).
    """
    v = (value or "").strip().replace("-", "").replace(" ", "")
    if not v.isdigit() or len(v) != 11:
        raise ValidationError("CUIT inválido: debe tener 11 dígitos.")
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    s = sum(int(d) * w for d, w in zip(v[:10], pesos))
    dv = 11 - (s % 11)
    if dv == 11:
        dv = 0
    elif dv == 10:
        dv = 9
    if dv != int(v[-1]):
        raise ValidationError("CUIT inválido: dígito verificador incorrecto.")


# ======================================================================================
# Choices centralizados
# ======================================================================================

class TipoPersona(models.TextChoices):
    FISICA = "FISICA", "Persona física"
    JURIDICA = "JURIDICA", "Persona jurídica"


class CondicionIVA(models.TextChoices):
    RI = "RI", "Responsable Inscripto"
    MONO = "MONO", "Monotributo"
    EXENTO = "EXENTO", "Exento"
    CF = "CF", "Consumidor Final"  # Caso base MVP


# ======================================================================================
# Modelo principal: Cliente
# ======================================================================================

class Cliente(models.Model):
    """
    Representa un cliente de un lavadero (empresa). Scope multi-tenant por empresa.
    Diseñado para búsquedas cotidianas (nombre/email/teléfono/documento) y
    relación con vehículos, ventas y notificaciones.
    """

    # --- Scope multi-tenant ---
    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="clientes",
        help_text="Lavadero propietario del cliente (aislamiento por empresa).",
    )

    # --- Identidad / Nombres ---
    tipo_persona = models.CharField(
        max_length=8,
        choices=TipoPersona.choices,
        default=TipoPersona.FISICA,
        help_text="Determina qué campos son obligatorios/esperados.",
    )
    nombre = models.CharField(max_length=120, blank=True)
    apellido = models.CharField(max_length=120, blank=True)
    razon_social = models.CharField(
        max_length=200,
        blank=True,
        help_text="Para personas jurídicas; opcional en físicas.",
    )

    # --- Identificadores ---
    documento = models.CharField(
        max_length=20,
        blank=True,
        help_text="DNI/CUIT u otro identificador. Único por empresa si no vacío.",
    )

    # --- Contacto ---
    email = models.EmailField(
        blank=True,
        validators=[EmailValidator(message="Email inválido.")],
        help_text="Único por empresa si no vacío.",
    )
    # Teléfono/WhatsApp en formato E.164 (p.ej. +549381XXXXXXX).
    tel_wpp = models.CharField(
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+[1-9]\d{7,14}$",
                message="Teléfono debe estar en formato internacional E.164 (p.ej. +549381123456).",
            )
        ],
        help_text="Formato E.164. Único por empresa si no vacío.",
    )
    # Campo derivado (sin símbolos) útil para búsquedas 'fuzzy'. Mantener desde services.
    tel_busqueda = models.CharField(
        max_length=20,
        blank=True,
        help_text="Teléfono sin símbolos para búsquedas rápidas (mantener en services).",
    )

    # --- Datos adicionales ---
    fecha_nac = models.DateField(null=True, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    localidad = models.CharField(max_length=120, blank=True)
    provincia = models.CharField(max_length=120, blank=True)
    cp = models.CharField("código postal", max_length=12, blank=True)

    # Segmentación simple; usar lista de strings en JSON.
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista de etiquetas simples (p.ej. ["vip", "empresa"]).',
    )

    # Notas libres
    notas = models.TextField(blank=True)

    # --- Meta/estado ---
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clientes_creados",
    )
    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["razon_social", "apellido", "nombre"]
        # Índices para búsquedas frecuentes por empresa + campo
        indexes = [
            models.Index(fields=["empresa", "nombre"]),
            models.Index(fields=["empresa", "apellido"]),
            models.Index(fields=["empresa", "razon_social"]),
            models.Index(fields=["empresa", "documento"]),
            models.Index(fields=["empresa", "tel_wpp"]),
            models.Index(fields=["empresa", "tel_busqueda"]),
            models.Index(fields=["empresa", "email"]),
        ]
        # Unicidades condicionales por empresa (cuando el campo no está vacío)
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "documento"],
                name="uniq_cliente_documento_por_empresa",
                condition=Q(documento__isnull=False) & ~Q(documento=""),
            ),
            models.UniqueConstraint(
                fields=["empresa", "email"],
                name="uniq_cliente_email_por_empresa",
                condition=Q(email__isnull=False) & ~Q(email=""),
            ),
            models.UniqueConstraint(
                fields=["empresa", "tel_wpp"],
                name="uniq_cliente_tel_por_empresa",
                condition=Q(tel_wpp__isnull=False) & ~Q(tel_wpp=""),
            ),
            # Regla de consistencia mínima de identidad:
            # al menos (nombre o razon_social) debe venir con algo.
            # (Regla fuerte está en clean(); aquí agregamos una verificación básica)
            models.CheckConstraint(
                name="chk_cliente_identidad_minima",
                check=(
                    Q(razon_social__isnull=False) & ~Q(razon_social="")
                )
                | (
                    (Q(nombre__isnull=False) & ~Q(nombre=""))
                    | (Q(apellido__isnull=False) & ~Q(apellido=""))
                ),
            ),
        ]

    # --------------------------- Métodos de dominio ---------------------------

    def clean(self) -> None:
        """
        Validaciones de negocio a nivel modelo.
        (Las normalizaciones ocurren en forms/services/normalizers.)
        """
        errors = {}

        # Reglas por tipo de persona:
        if self.tipo_persona == TipoPersona.FISICA:
            if not (self.nombre or self.apellido):
                errors["nombre"] = "Para persona física se requiere nombre y/o apellido."
        elif self.tipo_persona == TipoPersona.JURIDICA:
            if not self.razon_social:
                errors["razon_social"] = "Para persona jurídica se requiere razón social."

        # Email en blanco vs nulidad ya se controla arriba; aquí chequeamos case-insensitive?
        # (Si necesitás unicidad case-insensitive, mover a migración con índice funcional
        #  o normalizar a lower() en forms/services.)

        # Fecha de nacimiento no puede ser futura
        if self.fecha_nac and self.fecha_nac > timezone.localdate():
            errors["fecha_nac"] = "La fecha de nacimiento no puede ser futura."

        if errors:
            raise ValidationError(errors)

    # --------------------------- Helpers de presentación ---------------------------

    @property
    def display_name(self) -> str:
        """
        Nombre amigable para UI:
        - Jurídica: razón social
        - Física: 'Nombre Apellido' (lo que haya)
        """
        if self.tipo_persona == TipoPersona.JURIDICA and self.razon_social:
            return self.razon_social
        parts = [p for p in [self.nombre, self.apellido] if p]
        return " ".join(parts) if parts else "(Sin nombre)"

    @property
    def edad(self) -> Optional[int]:
        """Edad aproximada en años (None si falta fecha_nac)."""
        if not self.fecha_nac:
            return None
        today = timezone.localdate()
        years = today.year - self.fecha_nac.year
        if (today.month, today.day) < (self.fecha_nac.month, self.fecha_nac.day):
            years -= 1
        return years

    def cumple_hoy(self) -> bool:
        """True si hoy es su cumpleaños (ignora el año)."""
        if not self.fecha_nac:
            return False
        today = timezone.localdate()
        return (today.month, today.day) == (self.fecha_nac.month, self.fecha_nac.day)

    def __str__(self) -> str:  # pragma: no cover
        return self.display_name


# ======================================================================================
# Datos fiscales/facturación del cliente (opcional pero listo)
# ======================================================================================

class ClienteFacturacion(models.Model):
    """
    Información fiscal para facturación. OneToOne con Cliente.
    Útil cuando el comprobante necesita datos diferentes a los datos 'de contacto'.
    """
    cliente = models.OneToOneField(
        Cliente,
        on_delete=models.CASCADE,
        related_name="facturacion",
    )
    razon_social = models.CharField(
        max_length=200,
        help_text="Razón social para el comprobante.",
    )
    cuit = models.CharField(
        max_length=20,
        validators=[validar_cuit],
        help_text="CUIT (11 dígitos). Requerido salvo Consumidor Final.",
        blank=True,
    )
    cond_iva = models.CharField(
        max_length=6,
        choices=CondicionIVA.choices,
        default=CondicionIVA.CF,
        help_text="Condición frente al IVA del receptor del comprobante.",
    )
    domicilio_fiscal = models.CharField(max_length=255, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "datos de facturación"
        verbose_name_plural = "datos de facturación"
        constraints = [
            # Si no es Consumidor Final, exigir CUIT no vacío.
            models.CheckConstraint(
                name="chk_facturacion_cuit_requerido_si_no_cf",
                check=Q(cond_iva=CondicionIVA.CF)
                | (Q(cuit__isnull=False) & ~Q(cuit="")),
            )
        ]

    def clean(self) -> None:
        errors = {}

        # Consumidor Final → CUIT puede ir vacío; en otro caso, debe venir (validador ya verifica formato)
        if self.cond_iva != CondicionIVA.CF and not self.cuit:
            errors["cuit"] = "CUIT requerido para esta condición de IVA."
        # Coherencia básica con el cliente:
        # Si el cliente es jurídica y tiene razón_social, sugerimos mantenerla aquí.
        if (
            self.cliente.tipo_persona == TipoPersona.JURIDICA
            and self.razon_social.strip() == ""
        ):
            errors["razon_social"] = "Para persona jurídica, la razón social es obligatoria."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:  # pragma: no cover
        return f"Facturación de {self.cliente.display_name}"
