# apps/notifications/services/renderers.py
"""
Renderers para notificaciones (MVP, texto plano).

Responsabilidades:
- Construir el contexto de render a partir de una Venta y sus relaciones.
- Renderizar asunto/cuerpo usando el motor de plantillas de Django (texto plano).
- Tolerar faltantes con valores por defecto (render robusto, sin romper).

Variables soportadas (MVP):
    {{cliente.nombre}}, {{cliente.apellido}}, {{cliente.telefono}}
    {{vehiculo.patente}}, {{vehiculo.marca}}, {{vehiculo.modelo}}
    {{venta.id}}, {{venta.total}}, {{venta.estado}}
    {{empresa.nombre}}, {{sucursal.nombre}}
    {{venta.comprobante_url}}          (path o URL absoluta; ver SITE_BASE_URL)
    {{venta.comprobante_public_url}}   (igual que arriba; alias)
    {{nota_extra}}

Integraciones:
- Si existe un comprobante:
  - Se prioriza un link público: get_public_path() / get_public_url() o reverse('invoicing:public_view', public_key).
  - Si no hay público disponible, se cae a get_absolute_url() (requiere login).
- Si definís settings.SITE_BASE_URL (ej. "https://app.midominio.com"), se normaliza a URL absoluta
  para que los enlaces funcionen perfecto en WhatsApp.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from django.conf import settings
from django.template import Template, Context
from django.urls import reverse
from django.utils.safestring import mark_safe


@dataclass
class RenderResult:
    asunto: str
    cuerpo: str
    contexto: dict[str, Any]


DEFAULT_MISSING = "—"


def _safe(val: Any, default: str = DEFAULT_MISSING) -> str:
    if val is None:
        return default
    txt = str(val).strip()
    return txt if txt else default


def _abs_url(path_or_url: str) -> str:
    """
    Devuelve una URL absoluta si hay SITE_BASE_URL configurada y recibimos un path ("/...").
    Si ya viene con http(s), se devuelve tal cual.
    """
    val = (path_or_url or "").strip()
    if not val or val == DEFAULT_MISSING:
        return DEFAULT_MISSING
    if val.startswith("http://") or val.startswith("https://"):
        return val
    base = getattr(settings, "SITE_BASE_URL", "").strip().rstrip("/")
    return f"{base}{val}" if base else val


def _resolve_comprobante_url(venta) -> str:
    """
    Intenta resolver un link público primero; si no, usa el absoluto.
    Orden:
      1) comp.get_public_path() / comp.get_public_url()
      2) reverse('invoicing:public_view', public_key=...)
      3) comp.get_absolute_url()
    Luego normaliza a absoluta vía SITE_BASE_URL si existe.
    """
    try:
        comp = getattr(venta, "comprobante", None)
        if not comp:
            return DEFAULT_MISSING

        # 1) Métodos explícitos del modelo (si existen)
        if hasattr(comp, "get_public_path"):
            return _abs_url(comp.get_public_path() or DEFAULT_MISSING)
        if hasattr(comp, "get_public_url"):
            return _abs_url(comp.get_public_url() or DEFAULT_MISSING)

        # 2) Public key directa (si el modelo la tiene)
        public_key = getattr(comp, "public_key", None)
        if public_key:
            path = reverse("invoicing:public_view", kwargs={
                           "public_key": str(public_key)})
            return _abs_url(path)

        # 3) Fallback al detalle interno (requiere login)
        if hasattr(comp, "get_absolute_url"):
            return _abs_url(comp.get_absolute_url() or DEFAULT_MISSING)

    except Exception:
        pass

    return DEFAULT_MISSING


def build_context(venta, extras: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    Construye el contexto de plantilla a partir de `venta` y extras opcionales.
    No accede a request; solo usa relaciones/fks y campos básicos.
    """
    cliente = getattr(venta, "cliente", None)
    vehiculo = getattr(venta, "vehiculo", None)
    empresa = getattr(venta, "empresa", None)
    sucursal = getattr(venta, "sucursal", None)

    comprobante_url = _resolve_comprobante_url(venta)

    base = {
        "cliente": {
            "nombre": _safe(getattr(cliente, "nombre", None)),
            "apellido": _safe(getattr(cliente, "apellido", None)),
            "telefono": _safe(getattr(cliente, "tel_wpp", None)),
        },
        "vehiculo": {
            "patente": _safe(getattr(vehiculo, "patente", None)),
            "marca": _safe(getattr(vehiculo, "marca", None)),
            "modelo": _safe(getattr(vehiculo, "modelo", None)),
        },
        "venta": {
            "id": _safe(getattr(venta, "id", None)),
            "total": _safe(getattr(venta, "total", None)),
            "estado": _safe(getattr(venta, "estado", None)),
            "comprobante_url": _safe(comprobante_url),
            # alias útil en plantillas
            "comprobante_public_url": _safe(comprobante_url),
        },
        "empresa": {
            "nombre": _safe(getattr(empresa, "nombre", None)),
        },
        "sucursal": {
            "nombre": _safe(getattr(sucursal, "nombre", None)),
        },
        "nota_extra": _safe((extras or {}).get("nota_extra")) if extras else DEFAULT_MISSING,
    }

    # Merge superficial de extras por si se quieren variables adicionales
    if extras:
        for k, v in extras.items():
            if k not in base:
                base[k] = v

    return base


def _render_text(tpl_str: str, ctx: dict[str, Any]) -> str:
    """
    Renderiza un texto usando Django Template sin autoescape (texto plano).
    Evita fallar por None; el preprocesado pone "—" en faltantes.
    """
    tpl = Template(tpl_str or "")
    # autoescape Off: el contenido es texto plano, no HTML
    # texto plano intencional
    return mark_safe(tpl.render(Context(ctx, autoescape=False)))


def render(plantilla, venta, extras: Mapping[str, Any] | None = None) -> RenderResult:
    """
    Render principal: devuelve asunto y cuerpo con el contexto final utilizado.
    - asunto solo aplica cuando plantilla.es_email y asunto_tpl no está vacío.
    """
    ctx = build_context(venta, extras=extras)

    asunto = ""
    if getattr(plantilla, "es_email", False) and getattr(plantilla, "asunto_tpl", ""):
        asunto = _render_text(plantilla.asunto_tpl, ctx)

    cuerpo = _render_text(plantilla.cuerpo_tpl, ctx)

    return RenderResult(asunto=asunto, cuerpo=cuerpo, contexto=ctx)
