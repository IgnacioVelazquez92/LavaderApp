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
            f"Moneda inválida: '{moneda}'. Permitidas: {', '.join(permitidas)}"
        )


def validar_consistencia_empresa(instance) -> None:
    """
    Garantiza que sucursal, servicio y tipo_vehiculo pertenezcan a la misma empresa del registro.
    Seguro ante formularios incompletos (no desreferencia FKs si faltan).
    """
    emp_id = getattr(instance, "empresa_id", None)
    if not emp_id:
        # Sin empresa aún -> no validamos este punto.
        return

    errores: dict[str, str] = {}

    # Usamos *_id para evitar RelatedObjectDoesNotExist si el campo falta.
    if getattr(instance, "sucursal_id", None):
        from apps.org.models import Sucursal
        suc_emp = (
            Sucursal.objects.filter(pk=instance.sucursal_id)
            .values_list("empresa_id", flat=True)
            .first()
        )
        if suc_emp and suc_emp != emp_id:
            errores["sucursal"] = "La sucursal no pertenece a la empresa seleccionada."

    if getattr(instance, "servicio_id", None):
        from apps.catalog.models import Servicio
        srv_emp = (
            Servicio.objects.filter(pk=instance.servicio_id)
            .values_list("empresa_id", flat=True)
            .first()
        )
        if srv_emp and srv_emp != emp_id:
            errores["servicio"] = "El servicio no pertenece a la empresa seleccionada."

    if getattr(instance, "tipo_vehiculo_id", None):
        from apps.vehicles.models import TipoVehiculo
        tipo_emp = (
            TipoVehiculo.objects.filter(pk=instance.tipo_vehiculo_id)
            .values_list("empresa_id", flat=True)
            .first()
        )
        if tipo_emp and tipo_emp != emp_id:
            errores["tipo_vehiculo"] = "El tipo de vehículo no pertenece a la empresa seleccionada."

    if errores:
        # Mapear a campos específicos para que el form muestre cada error en su lugar.
        raise ValidationError(errores)


def validar_solapamiento_vigencias(instance) -> None:
    """
    Evita solapamiento de vigencias para la MISMA combinación (empresa, sucursal, servicio, tipo_vehiculo).

    Lógica de solapamiento (intervalos cerrados):
      Dos intervalos [a1, b1] y [a2, b2] solapan si:
        a1 <= b2 (o b2 es NULL -> infinito)  y  a2 <= b1 (o b1 es NULL -> infinito)

    Seguro ante formularios incompletos: si faltan claves mínimas (empresa, sucursal, servicio,
    tipo_vehiculo o vigencia_inicio), no valida y deja que los "required" del form actúen.
    """
    # Requisitos mínimos para validar solapamiento:
    if not getattr(instance, "empresa_id", None):
        return
    if not getattr(instance, "sucursal_id", None):
        return
    if not getattr(instance, "servicio_id", None):
        return
    if not getattr(instance, "tipo_vehiculo_id", None):
        return
    if not getattr(instance, "vigencia_inicio", None):
        return

    Model = instance.__class__

    qs = Model.objects.filter(
        empresa_id=instance.empresa_id,
        sucursal_id=instance.sucursal_id,
        servicio_id=instance.servicio_id,
        tipo_vehiculo_id=instance.tipo_vehiculo_id,
        activo=True,
    )
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)

    a2 = instance.vigencia_inicio
    b2 = instance.vigencia_fin  # puede ser None (abierto)

    if b2 is None:
        # [a2, +inf): solapa con (a1,b1) si a2 <= b1 (o b1 es NULL)
        overlap_q = Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=a2)
    else:
        # [a2, b2]: solapa si a1 <= b2  y  a2 <= b1 (o b1 es NULL)
        overlap_q = Q(vigencia_inicio__lte=b2) & (
            Q(vigencia_fin__isnull=True) | Q(vigencia_fin__gte=a2)
        )

    if qs.filter(overlap_q).exists():
        raise ValidationError(
            "Ya existe un precio vigente que se solapa en fechas para la misma "
            "Sucursal × Servicio × Tipo de vehículo. Cerrá la vigencia anterior o ajustá las fechas."
        )
