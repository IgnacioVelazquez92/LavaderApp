# apps/invoicing/services/emit.py
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.timezone import now

from apps.invoicing.models import Comprobante, TipoComprobante
from apps.invoicing.services.numbering import next_number
from apps.invoicing.services import renderers
from apps.sales.models import Venta
from apps.customers.models import ClienteFacturacion  # OneToOne con Cliente


@dataclass
class EmitirResultado:
    """Resultado del caso de uso de emisión."""
    comprobante: Comprobante
    creado: bool  # False si ya existía (idempotencia)


# -------------------------------
# Helpers de lectura tolerantes
# -------------------------------

def _items_qs(venta):
    """
    Devuelve un queryset de items tolerante al nombre del related.
    """
    mgr = getattr(venta, "items", None) or getattr(
        venta, "ventaitem_set", None)
    if mgr is None:
        return []
    try:
        return mgr.select_related("servicio").all().order_by("id")
    except Exception:
        return mgr.all().order_by("id")


def _ajustes_qs(venta):
    """
    Devuelve un iterable de ajustes aplicados a la venta (promos/desc.),
    tolerante a distintos related_names y nombres de FK al ítem: 'venta_item' o 'item'.
    """
    mgr = (
        getattr(venta, "ajustes", None)
        or getattr(venta, "salesadjustment_set", None)
        or getattr(venta, "adjustments", None)
    )
    if not mgr:
        return []

    # Detectar si el modelo tiene FK 'venta_item' o 'item'
    model = getattr(mgr, "model", None)
    item_field = None
    if model is not None:
        field_names = {f.name for f in model._meta.get_fields()}
        if "venta_item" in field_names:
            item_field = "venta_item"
        elif "item" in field_names:
            item_field = "item"

    # Armar select_related dinámico
    try:
        if item_field:
            return (
                mgr.select_related("promotion", item_field,
                                   f"{item_field}__servicio")
                .all()
                .order_by("id")
            )
        else:
            return mgr.select_related("promotion").all().order_by("id")
    except Exception:
        return mgr.all().order_by("id")


# -------------------------------
# Construcción del snapshot
# -------------------------------

def _build_snapshot(
    *,
    venta,
    tipo: str,
    numero_completo: str,
    punto_venta: int,
    cliente_facturacion: Optional[ClienteFacturacion] = None,
) -> Dict[str, Any]:
    """
    Genera el snapshot inmutable de la venta en el momento de emitir.
    Incluye: items, precio_lista, descuentos, total, payment_status, detalle de ajustes y,
    si corresponde, datos de cliente de facturación.
    """
    # Items
    items = []
    for it in _items_qs(venta):
        qty = getattr(it, "cantidad", 1)
        unit = Decimal(str(getattr(it, "precio_unitario", Decimal("0.00"))))
        subtotal_item = getattr(it, "subtotal", None)
        if subtotal_item is None:
            subtotal_item = qty * unit
        items.append({
            "servicio_id": it.servicio_id,
            "servicio_nombre": getattr(it.servicio, "nombre", ""),
            "cantidad": qty,
            "precio_unitario": str(unit),
            "subtotal": str(Decimal(str(subtotal_item))),
        })

    # Ajustes (promos/descuentos)
    # Ajustes (promos/descuentos)
    ajustes = []
    for adj in _ajustes_qs(venta):
        label = (
            getattr(getattr(adj, "promotion", None), "nombre", None)
            or getattr(adj, "motivo", None)
            or getattr(adj, "label", None)
            or "Ajuste"
        )
        monto = getattr(adj, "monto", None)
        if monto is None:
            monto = getattr(adj, "importe", Decimal("0.00"))
        es_porcentaje = bool(getattr(adj, "es_porcentaje", False))

        # Soportar FK al ítem con nombre 'venta_item' o 'item'
        item_obj = getattr(adj, "venta_item", None) or getattr(
            adj, "item", None)
        scope = "item" if item_obj is not None else "venta"
        target = getattr(getattr(item_obj, "servicio", None),
                         "nombre", None) if item_obj else None
        kind = "promo" if getattr(
            adj, "promotion_id", None) else "descuento_manual"

        # NUEVO: etiqueta ya resuelta para el template
        kind_label = "Promoción" if kind == "promo" else "Descuento"

        ajustes.append({
            "scope": scope,                         # "venta" | "item"
            "kind": kind,                           # "promo" | "descuento_manual"
            "kind_label": kind_label,               # <- NUEVO
            "label": label,                         # texto visible
            "monto": str(Decimal(str(monto))),      # monto absoluto
            "porcentaje": es_porcentaje,            # flag indicativo
            "target": target,                       # nombre de servicio si aplica
        })
    # Totales y flags de pago
    subtotal = Decimal(str(getattr(venta, "subtotal", Decimal("0.00"))))
    descuento = Decimal(str(getattr(venta, "descuento", Decimal("0.00"))))
    # no se imprime, pero queda en snapshot
    propina = Decimal(str(getattr(venta, "propina", Decimal("0.00"))))
    total = Decimal(str(getattr(venta, "total", Decimal("0.00"))))
    precio_lista = subtotal + descuento  # antes de aplicar descuentos/promos

    snapshot: Dict[str, Any] = {
        "comprobante": {
            "tipo": tipo,
            "numero": numero_completo,
            "emitido_en": now().isoformat(),
            "moneda": getattr(venta, "moneda", "ARS"),
        },
        "empresa": {
            "id": venta.empresa_id,
            "nombre": getattr(venta.empresa, "nombre", ""),
            "logo_data": _empresa_logo_base64(getattr(venta, "empresa", None)),
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
            "payment_status": getattr(venta, "payment_status", ""),
            "subtotal": str(subtotal),
            "descuento": str(descuento),
            "precio_lista": str(precio_lista),
            "propina": str(propina),
            "total": str(total),
            "saldo_pendiente": str(getattr(venta, "saldo_pendiente", Decimal("0.00"))),
            "notas": getattr(venta, "notas", ""),
        },
        "items": items,
        "ajustes": ajustes,
        "leyendas": {
            "no_fiscal": "Documento no fiscal.",
        },
    }

    # Incluir cliente de facturación si se usó
    if cliente_facturacion:
        snapshot["cliente_facturacion"] = {
            "razon_social": cliente_facturacion.razon_social,
            "cuit": cliente_facturacion.cuit,
            "cond_iva": str(cliente_facturacion.cond_iva),
            "domicilio_fiscal": cliente_facturacion.domicilio_fiscal or "",
        }

    # Validación mínima de serialización
    json.dumps(snapshot)
    return snapshot


# -------------------------------
# Caso de uso: emitir
# -------------------------------

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
    Emite un Comprobante para una venta pagada (payment_status='pagada').
    """
    venta = (
        Venta.objects
        .select_related("empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo")
        .prefetch_related("items__servicio")
        .get(pk=venta_id)
    )

    # 1) Validaciones de pago/proceso
    if getattr(venta, "payment_status", None) != "pagada":
        raise ValueError(
            "La venta no está pagada; no se puede emitir comprobante.")
    if getattr(venta, "estado", None) == "cancelado":
        raise ValueError(
            "La venta fue cancelada; no se puede emitir comprobante.")

    # 2) Idempotencia 1:1 (si ya existe, devolver)
    existente = getattr(venta, "comprobante", None)
    if existente:
        if reintentos_idempotentes:
            return EmitirResultado(comprobante=existente, creado=False)
        raise ValueError("La venta ya posee un comprobante emitido.")

    # 3) Tipo válido
    if tipo not in TipoComprobante.values:
        raise ValueError(f"Tipo de comprobante inválido: {tipo}")

    # 4) Cliente de facturación (opcional): debe ser del MISMO cliente de la venta
    cf: Optional[ClienteFacturacion] = None
    if cliente_facturacion_id is not None:
        cf = (
            ClienteFacturacion.objects
            .filter(pk=cliente_facturacion_id, cliente=venta.cliente)
            .first()
        )
        if cf is None:
            raise ValueError(
                "Cliente de facturación inválido para esta venta.")

    # 5) Numeración atómica
    numero_ctx = next_number(sucursal=venta.sucursal,
                             tipo=tipo, punto_venta=punto_venta)
    numero_completo = numero_ctx.numero_completo
    pv_real = int(numero_ctx.punto_venta)

    # 6) Snapshot y render (incluye cliente_facturacion si corresponde)
    snapshot = _build_snapshot(
        venta=venta,
        tipo=tipo,
        numero_completo=numero_completo,
        punto_venta=pv_real,
        cliente_facturacion=cf,
    )
    html = renderers.render_html({"snapshot": snapshot})
    pdf_bytes = renderers.html_to_pdf(html)  # Puede ser None

    # 7) Persistir comprobante
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

    # 8) Archivos
    comp.archivo_html.save(
        f"{comp.id}.html", ContentFile(html.encode("utf-8")))
    if pdf_bytes:
        comp.archivo_pdf.save(f"{comp.id}.pdf", ContentFile(pdf_bytes))

    return EmitirResultado(comprobante=comp, creado=True)


# ---------- Auto-emisión controlada (opcional) ----------

@transaction.atomic
def emitir_auto(*, venta_id, actor=None) -> Optional[EmitirResultado]:
    """
    Emite automáticamente si:
      - payment_status='pagada'
      - no está cancelada
      - no existe comprobante aún
    """
    venta = (
        Venta.objects
        .select_related("empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo")
        .get(pk=venta_id)
    )
    if getattr(venta, "payment_status", None) != "pagada":
        return None
    if getattr(venta, "estado", None) == "cancelado":
        return None
    if getattr(venta, "comprobante", None):
        return None

    return emitir(
        venta_id=venta.id,
        tipo=TipoComprobante.TICKET,
        punto_venta=1,
        cliente_facturacion_id=None,
        actor=actor,
        reintentos_idempotentes=True,
    )


# -------------------------------
# Utilidad: logo en base64
# -------------------------------

def _empresa_logo_base64(empresa) -> str | None:
    """
    Devuelve el logo como data URI base64 (png/jpg), o None si no hay.
    """
    logo = getattr(empresa, "logo", None)
    if not logo:
        return None
    try:
        with default_storage.open(logo.name, "rb") as f:
            data = f.read()
        ext = (logo.name.split(".")[-1] or "").lower()
        mime = "image/png" if ext in ("png",) else "image/jpeg"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None
