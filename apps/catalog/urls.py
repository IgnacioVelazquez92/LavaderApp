# apps/catalog/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    # Listado y CRUD de servicios
    path("catalogo/servicios/", views.ServiceListView.as_view(), name="services"),
    path("catalogo/servicios/nuevo/",
         views.ServiceCreateView.as_view(), name="service_new"),
    path("catalogo/servicios/<int:pk>/editar/",
         views.ServiceUpdateView.as_view(), name="service_edit"),
    path("catalogo/servicios/<int:pk>/detalle/",
         views.ServiceDetailView.as_view(), name="service_detail"),

    # Acciones POST (activar/desactivar)
    path("catalogo/servicios/<int:pk>/desactivar/",
         views.ServiceDeactivateView.as_view(), name="service_deactivate"),
    path("catalogo/servicios/<int:pk>/activar/",
         views.ServiceActivateView.as_view(), name="service_activate"),
]
