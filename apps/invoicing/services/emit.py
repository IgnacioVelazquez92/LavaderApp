# apps/invoicing/services/emit.py
from __future__ import annotations
import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.timezone import now
from apps.invoicing.models import Comprobante, TipoComprobante
from apps.invoicing.services.numbering import next_number
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

    IMPORTANTE:
    - Los montos de cada ajuste provienen de `SalesAdjustment.amount_applied`,
      que ya fue calculado/prorrateado en `recalcular_totales`.
    """

    # -----------------------
    # 1) Ítems de la venta
    # -----------------------
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

    # -----------------------
    # 2) Totales de la venta
    # -----------------------
    subtotal = Decimal(str(getattr(venta, "subtotal", Decimal("0.00"))))
    descuento = Decimal(str(getattr(venta, "descuento", Decimal("0.00"))))
    propina = Decimal(str(getattr(venta, "propina", Decimal("0.00"))))
    total = Decimal(str(getattr(venta, "total", Decimal("0.00"))))

    # Lo que mostramos como "Precio de lista":
    # base visible para el cliente. Si querés que sea "antes de descuentos",
    # usá: precio_lista = subtotal + descuento
    precio_lista = subtotal

    # -----------------------
    # 3) Ajustes (descuentos / promos)
    # -----------------------
    ajustes = []
    for adj in _ajustes_qs(venta):
        # Etiqueta visible
        label = (
            getattr(getattr(adj, "promotion", None), "nombre", None)
            or getattr(adj, "motivo", None)
            or getattr(adj, "label", None)
            or "Ajuste"
        )

        # Modo (percent / amount)
        mode = (getattr(adj, "mode", "") or "").lower()
        es_porcentaje = (mode == "percent")

        # Ítem asociado (si lo hay)
        item_obj = getattr(adj, "venta_item", None) or getattr(
            adj, "item", None)
        scope = "item" if item_obj is not None else "venta"
        target = getattr(getattr(item_obj, "servicio", None),
                         "nombre", None) if item_obj else None

        # Tipo de ajuste: promo vs descuento manual
        kind = "promo" if getattr(
            adj, "promotion_id", None) else "descuento_manual"
        kind_label = "Promoción" if kind == "promo" else "Descuento"

        # NUEVO: usar el monto realmente aplicado al descuento total
        raw_monto = getattr(adj, "amount_applied", None)
        if raw_monto is None:
            # fallback ultra defensivo para datos viejos (no debería usarse ya)
            raw_monto = Decimal("0.00")
        monto_dec = Decimal(str(raw_monto))

        ajustes.append({
            "scope": scope,                # "venta" | "item"
            "kind": kind,                  # "promo" | "descuento_manual"
            "kind_label": kind_label,      # "Promoción" / "Descuento"
            "label": label,                # texto visible (ej: "Familiar")
            "monto": str(monto_dec),       # monto REAL aplicado
            # alias por si algún template usa 'importe'
            "importe": str(monto_dec),
            "porcentaje": es_porcentaje,   # flag si viene de % originalmente
            "target": target,              # nombre de servicio si aplica
        })

    # -----------------------
    # 4) Armado del snapshot
    # -----------------------
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

    # Cliente de facturación (si corresponde)
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

    - Valida estado de la venta.
    - Garantiza idempotencia 1:1 (venta -> comprobante).
    - Calcula numeración.
    - Construye snapshot inmutable.
    - Persiste SOLO datos + snapshot (no guarda HTML/PDF en disco).
    """
    # 1) Cargar venta con relaciones necesarias
    venta = (
        Venta.objects
        .select_related("empresa", "sucursal", "cliente", "vehiculo", "vehiculo__tipo")
        .prefetch_related("items__servicio")
        .get(pk=venta_id)
    )

    # 2) Validaciones de pago/proceso
    if getattr(venta, "payment_status", None) != "pagada":
        raise ValueError(
            "La venta no está pagada; no se puede emitir comprobante.")

    if getattr(venta, "estado", None) == "cancelado":
        raise ValueError(
            "La venta fue cancelada; no se puede emitir comprobante.")

    # 3) Idempotencia 1:1 (si ya existe, devolver)
    existente = getattr(venta, "comprobante", None)
    if existente:
        if reintentos_idempotentes:
            return EmitirResultado(comprobante=existente, creado=False)
        raise ValueError("La venta ya posee un comprobante emitido.")

    # 4) Tipo válido
    if tipo not in TipoComprobante.values:
        raise ValueError(f"Tipo de comprobante inválido: {tipo}")

    # 5) Cliente de facturación (opcional): debe ser del MISMO cliente de la venta
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

    # 6) Numeración atómica
    numero_ctx = next_number(
        sucursal=venta.sucursal,
        tipo=tipo,
        punto_venta=punto_venta,
    )
    numero_completo = numero_ctx.numero_completo
    pv_real = int(numero_ctx.punto_venta)

    # 7) Snapshot inmutable (NO guardamos HTML/PDF acá)
    snapshot = _build_snapshot(
        venta=venta,
        tipo=tipo,
        numero_completo=numero_completo,
        punto_venta=pv_real,
        cliente_facturacion=cf,
    )

    # 8) Persistir comprobante con snapshot
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
