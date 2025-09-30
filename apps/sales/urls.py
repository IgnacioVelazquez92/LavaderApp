# apps/sales/urls.py
from django.urls import path
from . import views
from . import views_promotions

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


    # Descuentos / Promos
    path(
        "<uuid:pk>/descuentos/agregar/venta/",
        views_promotions.DiscountCreateOrderView.as_view(),
        name="discount_add_order",
    ),
    path(
        "<uuid:pk>/descuentos/agregar/item/",
        views_promotions.DiscountCreateItemView.as_view(),
        name="discount_add_item",
    ),
    path(
        "<uuid:pk>/descuentos/<int:adj_id>/eliminar/",
        views_promotions.DiscountDeleteView.as_view(),
        name="discount_delete",
    ),
    path(
        "<uuid:pk>/promos/aplicar/",
        views_promotions.PromotionApplyView.as_view(),
        name="promo_apply",
    ),

    path("promos/", views_promotions.PromotionListView.as_view(), name="promos_list"),
    path("promos/nueva/", views_promotions.PromotionCreateView.as_view(),
         name="promos_create"),
    path("promos/<int:pk>/editar/",
         views_promotions.PromotionUpdateView.as_view(), name="promos_edit"),
    path("promos/<int:pk>/eliminar/",
         views_promotions.PromotionDeleteView.as_view(), name="promos_delete"),
    path("promos/<int:pk>/toggle/",
         views_promotions.PromotionToggleActiveView.as_view(), name="promos_toggle"),
]
