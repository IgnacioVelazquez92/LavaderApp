# apps/notifications/urls.py
from django.urls import path
from .views import (
    TemplateListView,
    TemplateCreateView,
    TemplateUpdateView,
    PreviewView,
    LogListView,
    SendFromSaleView
)

app_name = "notifications"

urlpatterns = [
    # Plantillas (CRUD básico)
    path("plantillas/", TemplateListView.as_view(), name="templates_list"),
    path("plantillas/nueva/", TemplateCreateView.as_view(), name="template_create"),
    path("plantillas/<uuid:pk>/editar/",
         TemplateUpdateView.as_view(), name="template_update"),

    # Preview
    path("preview/", PreviewView.as_view(), name="preview"),

    # Logs (opcional)
    path("logs/", LogListView.as_view(), name="logs_list"),
    path(
        "ventas/<uuid:venta_id>/notificar/",
        SendFromSaleView.as_view(),
        # <- este name es el que usás en reverse(...)
        name="send_from_sale",
    ),
]
