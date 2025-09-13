# apps/pricing/validators.py
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q


def validar_moneda(moneda: str, permitidas: list[str] | None = None) -> None:
    """
    Verifica que la moneda esté dentro del catálogo permitido.
    """
    if permitidas is None:
        permitidas = ["ARS", "USD"]
    if moneda not in permitidas:
        raise ValidationError(
            f"Moneda inválida: '{moneda}'. Permitidas: {', '.join(permitidas)}")


def validar_consistencia_empresa(instance) -> None:
    """
    Garantiza que sucursal, servicio y tipo_vehiculo pertenezcan a la misma empresa del registro.
    """
    errores = []

    if instance.sucursal and instance.sucursal.empresa_id != instance.empresa_id:
        errores.append("La sucursal no pertenece a la empresa seleccionada.")
    if instance.servicio and instance.servicio.empresa_id != instance.empresa_id:
        errores.append("El servicio no pertenece a la empresa seleccionada.")
    if instance.tipo_vehiculo and instance.tipo_vehiculo.empresa_id != instance.empresa_id:
        errores.append(
            "El tipo de vehículo no pertenece a la empresa seleccionada.")

    if errores:
        raise ValidationError(errores)


def validar_solapamiento_vigencias(instance) -> None:
    """
    Evita solapamiento de vigencias para la MISMA combinación (empresa, sucursal, servicio, tipo_vehiculo).

    Lógica de solapamiento (intervalos cerrados):
      Dos intervalos [a1, b1] y [a2, b2] solapan si:
        a1 <= b2 (o b2 es NULL -> infinito)  y  a2 <= b1 (o b1 es NULL -> infinito)
    """
    Model = instance.__class__

    qs = Model.objects.filter(
        empresa=instance.empresa,
        sucursal=instance.sucursal,
        servicio=instance.servicio,
        tipo_vehiculo=instance.tipo_vehiculo,
        activo=True,
    )
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)

    a2 = instance.vigencia_inicio
    b2 = instance.vigencia_fin  # puede ser None (abierto)

    if b2 is None:
        # [a2, +inf): solapa con (a1,b1) si a1 <= +inf (siempre True) y a2 <= b1 (o b1 es NULL)
        overlap_q = Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=a2)
    else:
        # [a2, b2]: solapa con (a1,b1) si a1 <= b2  y  a2 <= b1 (o b1 es NULL)
        overlap_q = (
            Q(vigencia_inicio__lte=b2) &
            (Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=a2))
        )

    if qs.filter(overlap_q).exists():
        raise ValidationError(
            "Ya existe un precio vigente que se solapa en fechas para la misma "
            "Sucursal × Servicio × Tipo de vehículo. Cerrá la vigencia anterior o ajustá las fechas."
        )
