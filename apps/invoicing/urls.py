# apps/invoicing/urls.py
from __future__ import annotations

from django.urls import path

from .views import (
    ComprobanteListView,
    ComprobanteDetailView,
    ComprobanteDownloadView,
    EmitirComprobanteView,
)

app_name = "invoicing"

urlpatterns = [
    # ------------------------------------------------------------------
    # LISTADO / DETALLE / DESCARGA DE COMPROBANTES
    # ------------------------------------------------------------------
    # GET /comprobantes/?sucursal=<id>&tipo=<TICKET|REMITO>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    path("comprobantes/", ComprobanteListView.as_view(), name="list"),

    # GET /comprobantes/<uuid:pk>/
    path("comprobantes/<uuid:pk>/", ComprobanteDetailView.as_view(), name="detail"),

    # GET /comprobantes/<uuid:pk>/descargar/
    path("comprobantes/<uuid:pk>/descargar/",
         ComprobanteDownloadView.as_view(), name="download"),

    # ------------------------------------------------------------------
    # EMISIÓN DESDE UNA VENTA (IDEMPOTENTE)
    # ------------------------------------------------------------------
    # GET/POST /ventas/<uuid:venta_id>/emitir/
    # Nota: Lo exponemos bajo /ventas/ para que el flujo parta de la Venta.
    path("ventas/<uuid:venta_id>/emitir/",
         EmitirComprobanteView.as_view(), name="emit"),
]
