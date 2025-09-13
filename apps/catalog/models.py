# apps/catalog/models.py
from __future__ import annotations

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from django.utils.text import slugify


class ServicioQuerySet(models.QuerySet):
    """
    Consultas reutilizables para Servicio.
    Útil para selectors y vistas.
    """

    def para_empresa(self, empresa: "Empresa") -> "ServicioQuerySet":
        """Filtra por empresa (tenant)."""
        return self.filter(empresa=empresa)

    def activos(self) -> "ServicioQuerySet":
        """Solo servicios activos."""
        return self.filter(activo=True)

    def buscar(self, q: str) -> "ServicioQuerySet":
        """
        Búsqueda simple por nombre (case-insensitive).
        Nota: mantener alineado con selectors.buscar_servicio().
        """
        q = (q or "").strip()
        if not q:
            return self
        return self.filter(nombre__icontains=q)


class Servicio(models.Model):
    """
    Catálogo de servicios ofrecidos por el lavadero.

    - Scoping multi-tenant por Empresa.
    - Unicidad de nombre por empresa (case-insensitive).
    - `slug` único por empresa para URL/refs internas.
    """

    empresa = models.ForeignKey(
        "org.Empresa",
        on_delete=models.CASCADE,
        related_name="servicios",
        verbose_name="Empresa",
        help_text="Empresa (tenant) a la que pertenece el servicio.",
    )

    nombre = models.CharField(
        "Nombre",
        max_length=120,
        help_text="Nombre del servicio (p. ej., Lavado exterior, Encerado).",
    )

    slug = models.SlugField(
        "Slug",
        max_length=140,
        blank=True,
        help_text="Identificador URL-safe; si se deja vacío se genera automáticamente.",
    )

    descripcion = models.TextField(
        "Descripción",
        blank=True,
        default="",
        help_text="Descripción breve u observaciones del servicio (opcional).",
    )

    activo = models.BooleanField(
        "Activo",
        default=True,
        help_text="Si está desmarcado, el servicio no aparece para nuevas ventas/precios.",
    )

    creado = models.DateTimeField("Creado", auto_now_add=True)
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    # Managers
    objects = ServicioQuerySet.as_manager()

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = [Lower("nombre"), "id"]
        indexes = [
            models.Index(fields=["empresa", "activo"],
                         name="svc_empresa_activo_idx"),
            models.Index(fields=["empresa", "nombre"],
                         name="svc_empresa_nombre_idx"),
        ]
        constraints = [
            # Unicidad de nombre por empresa (case-insensitive)
            UniqueConstraint(
                Lower("nombre"),
                "empresa",
                name="uniq_servicio_nombre_ci_por_empresa",
            ),
            # Unicidad de slug por empresa (solo cuando slug no está vacío)
            UniqueConstraint(
                fields=["empresa", "slug"],
                name="uniq_servicio_slug_por_empresa",
                # Para compatibilidad cross-DB, no usamos condición; generamos slug único en save().
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover (representación simple)
        return self.nombre

    # ----------------------------
    # Validaciones y utilidades
    # ----------------------------
    def clean(self):
        """
        Normalizaciones mínimas previas a validación:
        - recorta espacios en nombre y descripción.
        """
        if self.nombre:
            self.nombre = self.nombre.strip()
        if self.descripcion:
            self.descripcion = self.descripcion.strip()

    def save(self, *args, **kwargs):
        """
        Genera `slug` único por empresa si está vacío o si el nombre cambió y no hay slug.
        """
        # Normalización defensiva
        if self.nombre:
            self.nombre = " ".join(self.nombre.split())

        # Autogenerar slug si corresponde
        if not self.slug and self.nombre:
            self.slug = self._build_unique_slug()

        super().save(*args, **kwargs)

    # ----------------------------
    # Helpers internos
    # ----------------------------
    def _build_unique_slug(self) -> str:
        """
        Crea un slug único dentro de la empresa.
        Evita colisiones añadiendo sufijos -2, -3, ...
        """
        base = slugify(self.nombre) or "servicio"
        candidate = base
        n = 2
        while (
            Servicio.objects.filter(empresa=self.empresa, slug=candidate)
            .exclude(pk=self.pk)
            .exists()
        ):
            candidate = f"{base}-{n}"
            n += 1
            if n > 9999:  # límite de seguridad para evitar loops
                break
        return candidate
