# apps/saas/urls.py
"""
Rutas del módulo SaaS (MVP público).

- /saas/panel/           → Panel informativo de la empresa activa
- /saas/planes/          → Catálogo público de planes (usuarios autenticados)
- /saas/upgrade/         → Acción POST para "Solicitar upgrade" (MVP)
"""

from __future__ import annotations

from django.urls import path

from .views import (
    SaaSPanelView,
    PlanesPublicListView,
    SolicitarUpgradeView,
)

app_name = "saas"

urlpatterns = [
    path("panel/", SaaSPanelView.as_view(), name="panel"),
    path("planes/", PlanesPublicListView.as_view(), name="planes_public"),
    path("upgrade/", SolicitarUpgradeView.as_view(), name="solicitar_upgrade"),
]
