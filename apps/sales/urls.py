# apps/sales/urls.py
from django.urls import path
from .views import (
    VentaListView,
    VentaCreateView,
    VentaDetailView,
    AgregarItemView,
    ActualizarItemView,
    EliminarItemView,
    FinalizarVentaView,
    CancelarVentaView,
)

app_name = "sales"

urlpatterns = [
    # Listado y creación
    path("", VentaListView.as_view(), name="list"),
    path("nueva/", VentaCreateView.as_view(), name="create"),

    # Detalle de venta
    path("<uuid:pk>/", VentaDetailView.as_view(), name="detail"),

    # Ítems
    path("<uuid:pk>/items/agregar/", AgregarItemView.as_view(), name="item_add"),
    path(
        "<uuid:pk>/items/<int:item_id>/actualizar/",
        ActualizarItemView.as_view(),
        name="item_update",
    ),
    path(
        "<uuid:pk>/items/<int:item_id>/eliminar/",
        EliminarItemView.as_view(),
        name="item_delete",
    ),

    # Acciones de estado
    path("<uuid:pk>/finalizar/", FinalizarVentaView.as_view(), name="finalize"),
    path("<uuid:pk>/cancelar/", CancelarVentaView.as_view(), name="cancel"),
]
