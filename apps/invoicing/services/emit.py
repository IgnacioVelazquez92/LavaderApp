# apps/invoicing/services/emit.py
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import now

from apps.invoicing.models import Comprobante, ClienteFacturacion, TipoComprobante
from apps.invoicing.services.numbering import next_number
from apps.invoicing.services import renderers
from apps.sales.models import Venta


@dataclass
class EmitirResultado:
    """Resultado del caso de uso de emisión."""
    comprobante: Comprobante
    creado: bool  # False si ya existía (idempotencia)


def _items_qs(venta):
    """
    Devuelve un queryset de items tolerante al nombre del related:
    usa 'items' si existe (tu caso), o cae a 'ventaitem_set' si no.
    """
    mgr = getattr(venta, "items", None) or getattr(
        venta, "ventaitem_set", None)
    if mgr is None:
        return []
    try:
        return mgr.select_related("servicio").all().order_by("id")
    except Exception:
        # fallback súper defensivo
        return mgr.all().order_by("id")


def _build_snapshot(*, venta, tipo: str, numero_completo: str, punto_venta: int) -> Dict[str, Any]:
    """
    Genera el snapshot inmutable de la venta en el momento de emitir.
    Mantenerlo plano, autocontenible y serializable a JSON sin pérdidas.
    """
    items = []
    for it in _items_qs(venta):
        items.append({
            "servicio_id": it.servicio_id,
            "servicio_nombre": getattr(it.servicio, "nombre", ""),
            "cantidad": getattr(it, "cantidad", 1),
            "precio_unitario": str(getattr(it, "precio_unitario", Decimal("0.00"))),
            # usa @property en tu modelo
            "subtotal": str(getattr(it, "subtotal", Decimal("0.00"))),
        })

    snapshot = {
        "comprobante": {
            "tipo": tipo,
            "numero": numero_completo,
            "emitido_en": now().isoformat(),
            "moneda": getattr(venta, "moneda", "ARS"),
        },
        "empresa": {
            "id": venta.empresa_id,
            "nombre": getattr(venta.empresa, "nombre", ""),
        },
        "sucursal": {
            "id": venta.sucursal_id,
            "nombre": getattr(venta.sucursal, "nombre", ""),
            "punto_venta": str(punto_venta),
        },
        "cliente": {
            "id": venta.cliente_id,
            "nombre": getattr(venta.cliente, "nombre", ""),
            "apellido": getattr(venta.cliente, "apellido", ""),
        },
        "vehiculo": {
            "id": venta.vehiculo_id,
            "patente": getattr(venta.vehiculo, "patente", ""),
            "tipo": getattr(getattr(venta.vehiculo, "tipo", None), "nombre", ""),
        },
        "venta": {
            "id": str(venta.id),
            "estado": getattr(venta, "estado", ""),
            "subtotal": str(getattr(venta, "subtotal", Decimal("0.00"))),
            "propina": str(getattr(venta, "propina", Decimal("0.00"))),
            "descuento": str(getattr(venta, "descuento", Decimal("0.00"))),
            "total": str(getattr(venta, "total", Decimal("0.00"))),
            "saldo_pendiente": str(getattr(venta, "saldo_pendiente", Decimal("0.00"))),
            "notas": getattr(venta, "notas", ""),
        },
        "items": items,
        "leyendas": {
            "no_fiscal": "Documento no fiscal.",
        },
    }

    # Validación mínima de serialización (por si algo raro se cuela)
    json.dumps(snapshot)
    return snapshot


@transaction.atomic
def emitir(
    *,
    venta_id,
    tipo: str,
    punto_venta: int = 1,
    cliente_facturacion_id: Optional[int] = None,
    actor=None,
    reintentos_idempotentes: bool = True,
) -> EmitirResultado:
    """
    Emite un Comprobante para una venta 'pagada'.

    Flujo:
      1) Carga y valida Venta (estado 'pagado'; 1-venta-1-comprobante).
      2) Idempotencia: si ya existe y reintentos=True → devolverlo.
      3) Obtiene numeración atómica por (sucursal, tipo, punto_venta).
      4) Construye snapshot (inmutable).
      5) Renderiza HTML (y PDF opcional) y persiste archivos + registro.

    Reglas:
      - Sincroniza empresa/sucursal mediante la venta (no pasa por request).
      - Cliente de facturación opcional; si se pasa, debe pertenecer a la misma empresa.
    """
    venta = (
        Venta.objects
        .select_related("empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo")
        .prefetch_related("items__servicio")
        .get(pk=venta_id)
    )
    # 1) Validación de estado
    if getattr(venta, "estado", None) != "pagado":
        raise ValueError(
            "La venta no está en estado 'pagado'; no se puede emitir comprobante.")

    # 2) Idempotencia 1:1 (MVP)
    existente = getattr(venta, "comprobante", None)
    if existente:
        if reintentos_idempotentes:
            return EmitirResultado(comprobante=existente, creado=False)
        raise ValueError("La venta ya posee un comprobante emitido.")

    # 3) Validación de tipo
    if tipo not in TipoComprobante.values:
        raise ValueError(f"Tipo de comprobante inválido: {tipo}")

    # 4) Numeración atómica
    numero_ctx = next_number(sucursal=venta.sucursal,
                             tipo=tipo, punto_venta=punto_venta)
    numero_completo = numero_ctx.numero_completo  # ej. "0001-00001234"
    pv_real = int(numero_ctx.punto_venta)

    # 5) Snapshot y render
    snapshot = _build_snapshot(
        venta=venta,
        tipo=tipo,
        numero_completo=numero_completo,
        punto_venta=pv_real,
    )

    html = renderers.render_html({"snapshot": snapshot})
    pdf_bytes = renderers.html_to_pdf(html)  # Puede devolver None/bytes

    # 6) Cliente de facturación (opcional, misma empresa)
    cf = None
    if cliente_facturacion_id is not None:
        cf = (
            ClienteFacturacion.objects
            .filter(pk=cliente_facturacion_id, empresa=venta.empresa)
            .first()
        )
        if cf is None:
            raise ValueError(
                "Cliente de facturación inválido para la empresa actual.")

    # 7) Persistencia del comprobante
    comp = Comprobante.objects.create(
        empresa=venta.empresa,
        sucursal=venta.sucursal,
        venta=venta,
        cliente=venta.cliente,
        cliente_facturacion=cf,
        tipo=tipo,
        punto_venta=pv_real,
        numero=numero_ctx.numero,
        moneda=snapshot["comprobante"]["moneda"],
        total=venta.total,
        snapshot=snapshot,
        emitido_por=actor,
    )

    # 8) Guardar archivos (HTML obligatorio; PDF si disponible)
    comp.archivo_html.save(
        f"{comp.id}.html", ContentFile(html.encode("utf-8")))
    if pdf_bytes:
        comp.archivo_pdf.save(f"{comp.id}.pdf", ContentFile(pdf_bytes))

    return EmitirResultado(comprobante=comp, creado=True)


# ---------- OPCIONAL: auto-emisión controlada (apagada por defecto) ----------

@transaction.atomic
def emitir_auto(*, venta_id, actor=None) -> Optional[EmitirResultado]:
    """
    Emite con defaults cuando:
      - La venta está 'pagado'
      - Aún no existe comprobante para esa venta (idempotente)
    Defaults:
      - tipo = TICKET
      - punto_venta = 1 (o la heurística que definas externamente)
    Devuelve:
      - EmitirResultado si creó
      - None si no aplicaba (no pagada o ya tenía comprobante)
    """
    venta = (
        Venta.objects
        .select_related("empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo")
        .get(pk=venta_id)
    )
    if venta.estado != "pagado":
        return None
    if getattr(venta, "comprobante", None):
        return None

    # Si más adelante definís un PV por sucursal, ajustá este valor aquí.
    pv = 1
    return emitir(
        venta_id=venta.id,
        tipo=TipoComprobante.TICKET,
        punto_venta=pv,
        cliente_facturacion_id=None,
        actor=actor,
        reintentos_idempotentes=True,
    )
