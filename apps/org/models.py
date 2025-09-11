# apps/org/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class Empresa(models.Model):
    """
    Tenant raíz del sistema (ej. 'Lavadero El Sol').
    Cada usuario puede tener membresías a una o varias empresas.
    """
    nombre = models.CharField(_("Nombre"), max_length=150)
    subdominio = models.SlugField(
        _("Subdominio"),
        max_length=50,
        unique=True,
        help_text=_(
            "Identificador único en la URL (ej: misucursal.lavaderosapp.com)"),
    )
    logo = models.ImageField(
        _("Logo"),
        upload_to="empresas/logos/",
        null=True,
        blank=True,
    )
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Empresa")
        verbose_name_plural = _("Empresas")

    def __str__(self):
        return self.nombre


class EmpresaConfig(models.Model):
    """
    Configuración extensible por empresa (par clave/valor).
    Útil para flags, preferencias, integraciones.
    """
    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="configs")
    clave = models.CharField(max_length=100)
    valor = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("empresa", "clave")
        verbose_name = _("Configuración de Empresa")
        verbose_name_plural = _("Configuraciones de Empresa")

    def __str__(self):
        return f"{self.empresa.nombre} - {self.clave}"


class Sucursal(models.Model):
    """
    Local físico de una empresa.
    """
    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="sucursales")
    nombre = models.CharField(_("Nombre"), max_length=100)
    direccion = models.CharField(_("Dirección"), max_length=255, blank=True)
    codigo_interno = models.CharField(
        _("Código interno"),
        max_length=20,
        help_text=_("Código único dentro de la empresa"),
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("empresa", "codigo_interno")
        verbose_name = _("Sucursal")
        verbose_name_plural = _("Sucursales")

    def __str__(self):
        return f"{self.nombre} ({self.empresa.nombre})"

    def save(self, *args, **kwargs):
        if not self.codigo_interno:
            base = (slugify(self.nombre).upper() or "S")
            # tomar primeras 6 para que sea corto
            base = base[:6]
            # buscar siguiente número disponible
            n = 1
            while True:
                cand = f"{base}{n:02d}"
                if not Sucursal.objects.filter(empresa=self.empresa, codigo_interno=cand).exists():
                    self.codigo_interno = cand
                    break
                n += 1
        super().save(*args, **kwargs)
