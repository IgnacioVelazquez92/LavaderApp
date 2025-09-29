# apps/sales/urls.py
from django.urls import path
from . import views

app_name = "sales"

urlpatterns = [
    # Listado y creación
    path("", views.VentaListView.as_view(), name="list"),
    path("nueva/", views.VentaCreateView.as_view(), name="create"),

    # Detalle de venta
    path("<uuid:pk>/", views.VentaDetailView.as_view(), name="detail"),

    # Ítems
    path("<uuid:pk>/items/agregar/",
         views.AgregarItemView.as_view(), name="item_add"),
    path(
        "<uuid:pk>/items/<int:item_id>/actualizar/",
        views.ActualizarItemView.as_view(),
        name="item_update",
    ),
    path(
        "<uuid:pk>/items/<int:item_id>/eliminar/",
        views.EliminarItemView.as_view(),
        name="item_delete",
    ),

    # Acciones de estado
    path("<uuid:pk>/iniciar/", views.IniciarVentaView.as_view(), name="start"),
    path("<uuid:pk>/finalizar/", views.FinalizarVentaView.as_view(), name="finalize"),
    path("<uuid:pk>/cancelar/", views.CancelarVentaView.as_view(), name="cancel"),
]
