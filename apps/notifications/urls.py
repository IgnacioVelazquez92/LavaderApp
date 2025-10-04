from django.urls import path
from .views import (
    TemplateListView,
    TemplateCreateView,
    TemplateUpdateView,
    PreviewView,
    LogListView,
    SendFromSaleView,
)
from .views_email import (
    EmailServerListView,
    EmailServerCreateView,
    EmailServerUpdateView,
    EmailServerDeleteView,
    emailserver_test_connection_view,
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

    # Logs
    path("logs/", LogListView.as_view(), name="logs_list"),

    # Enviar notificación desde venta
    path("ventas/<uuid:venta_id>/notificar/",
         SendFromSaleView.as_view(), name="send_from_sale"),

    # Email Servers (SMTP)
    path("emailservers/", EmailServerListView.as_view(), name="emailserver_list"),
    path("emailservers/nuevo/", EmailServerCreateView.as_view(),
         name="emailserver_create"),
    path("emailservers/<int:pk>/editar/",
         EmailServerUpdateView.as_view(), name="emailserver_update"),
    path("emailservers/<int:pk>/eliminar/",
         EmailServerDeleteView.as_view(), name="emailserver_delete"),
    path("emailservers/<int:pk>/probar/",
         emailserver_test_connection_view, name="emailserver_test"),
]
