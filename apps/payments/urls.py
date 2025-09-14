# apps/payments/urls.py
from django.urls import path
from apps.payments.views import PaymentCreateView, PaymentListView
from apps.payments.views_medios import (
    MedioPagoListView, MedioPagoCreateView, MedioPagoUpdateView, MedioPagoToggleActivoView
)

app_name = "payments"

urlpatterns = [
    # Pagos
    path("ventas/<uuid:venta_id>/pagos/nuevo/",
         PaymentCreateView.as_view(), name="create"),
    path("pagos/", PaymentListView.as_view(), name="list"),

    # Medios de pago (CRUD)
    path("medios/", MedioPagoListView.as_view(), name="medios_list"),
    path("medios/nuevo/", MedioPagoCreateView.as_view(), name="medios_create"),
    path("medios/<int:pk>/editar/",
         MedioPagoUpdateView.as_view(), name="medios_update"),
    path("medios/<int:pk>/toggle/",
         MedioPagoToggleActivoView.as_view(), name="medios_toggle"),
]
