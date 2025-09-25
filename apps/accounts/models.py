# apps/accounts/models.py
from django.conf import settings
from django.db import models


class EmpresaMembership(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_OPERADOR = "operador"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrador"),
        (ROLE_OPERADOR, "Operador"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="empresa_memberships")
    empresa = models.ForeignKey(
        "org.Empresa", on_delete=models.CASCADE, related_name="memberships")
    rol = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=ROLE_OPERADOR)

    # NUEVO
    sucursal_asignada = models.ForeignKey(
        "org.Sucursal", on_delete=models.SET_NULL, null=True, blank=True, related_name="empleados"
    )
    is_owner = models.BooleanField(default=False)     # el que creó el lavadero
    # habilitado/deshabilitado dentro de esta empresa
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "empresa")
        verbose_name = "Membresía de Empresa"
        verbose_name_plural = "Membresías de Empresa"

    def __str__(self):
        return f"{self.user} → {self.empresa} ({self.rol})"
