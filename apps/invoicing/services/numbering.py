from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.invoicing.models import SecuenciaComprobante, TipoComprobante


@dataclass(frozen=True)
class NumeroComprobante:
    """DTO simple para retornar el nuevo número con su contexto."""
    tipo: str
    punto_venta: str
    numero: int

    @property
    def numero_completo(self) -> str:
        return f"{str(self.punto_venta).zfill(4)}-{str(self.numero).zfill(8)}"


@transaction.atomic
def next_number(*, sucursal, tipo: str, punto_venta: str = "1") -> NumeroComprobante:
    """
    Incrementa de forma ATÓMICA la secuencia por (sucursal, tipo, punto_venta).

    Reglas:
      - Crea la secuencia si no existe (arranca en 1).
      - SELECT ... FOR UPDATE para bloquear la fila en la transacción.
      - Devuelve el número ASIGNADO (no el próximo).
    """
    if tipo not in TipoComprobante.values:
        raise ValueError(f"TipoComprobante inválido: {tipo}")

    # Bloqueo pesimista para evitar carreras de concurrencia.
    seq = (
        SecuenciaComprobante.objects
        .select_for_update()
        .filter(sucursal=sucursal, tipo=tipo, punto_venta=punto_venta)
        .first()
    )

    if seq is None:
        # Crear y bloquear inmediatamente.
        seq = SecuenciaComprobante.objects.create(
            sucursal=sucursal, tipo=tipo, punto_venta=punto_venta, proximo_numero=1
        )
        # Releer con lock para consistencia (en la práctica no es estrictamente necesario aquí).
        seq = (
            SecuenciaComprobante.objects
            .select_for_update()
            .get(pk=seq.pk)
        )

    numero_asignado = seq.proximo_numero
    seq.proximo_numero = numero_asignado + 1
    seq.save(update_fields=["proximo_numero", "actualizado_en"])

    return NumeroComprobante(tipo=tipo, punto_venta=punto_venta, numero=numero_asignado)
