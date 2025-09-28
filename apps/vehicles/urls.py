"""
urls.py — Rutas del módulo Vehicles
Convenciones:
- Namespace = "vehicles"
- Prefijos claros: /vehiculos/... y /tipos-vehiculo/...
"""

from django.urls import path
from . import views

app_name = "vehicles"

urlpatterns = [
    # ==========================
    # Vehículos
    # ==========================
    path("", views.VehicleListView.as_view(), name="list"),
    path("nuevo/", views.VehicleCreateView.as_view(), name="new"),
    path("<int:pk>/editar/", views.VehicleUpdateView.as_view(), name="edit"),
    path("<int:pk>/detalle/", views.VehicleDetailView.as_view(), name="detail"),
    path("<int:pk>/activar/", views.VehicleActivateView.as_view(), name="activate"),
    path("<int:pk>/desactivar/",
         views.VehicleDeactivateView.as_view(), name="deactivate"),

    # ==========================
    # Tipos de vehículo
    # ==========================
    path("tipos-vehiculo/", views.TipoVehiculoListView.as_view(), name="types_list"),
    path("tipos-vehiculo/nuevo/",
         views.TipoVehiculoCreateView.as_view(), name="types_new"),
    path("tipos-vehiculo/<int:pk>/editar/",
         views.TipoVehiculoUpdateView.as_view(), name="types_edit"),
    path("tipos-vehiculo/<int:pk>/activar/",
         views.TipoVehiculoActivateView.as_view(), name="types_activate"),
    path("tipos-vehiculo/<int:pk>/desactivar/",
         views.TipoVehiculoDeactivateView.as_view(), name="types_deactivate"),
    path("tipos-vehiculo/<int:pk>/eliminar/",
         views.VehicleTypeDeleteView.as_view(), name="types_delete"),
]
