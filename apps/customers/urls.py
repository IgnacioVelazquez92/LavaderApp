from django.urls import path

from .views import (
    CustomerListView,
    CustomerCreateView,
    CustomerUpdateView,
    CustomerDetailView,
)

app_name = "customers"

urlpatterns = [
    path("", CustomerListView.as_view(), name="list"),
    path("nuevo/", CustomerCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", CustomerUpdateView.as_view(), name="update"),
    path("<int:pk>/detalle/", CustomerDetailView.as_view(), name="detail"),
]
