# apps/pricing/urls.py
from __future__ import annotations

from django.urls import path

from .views import (
    PriceListView,
    PriceCreateView,
    PriceUpdateView,
    PriceDeactivateView
)

app_name = "pricing"

urlpatterns = [
    # Listado + filtros
    path("", PriceListView.as_view(), name="list"),

    # Alta
    path("nuevo/", PriceCreateView.as_view(), name="create"),

    # Edición
    path("<int:pk>/editar/", PriceUpdateView.as_view(), name="edit"),
    path("<int:pk>/desactivar/", PriceDeactivateView.as_view(), name="deactivate"),
]
