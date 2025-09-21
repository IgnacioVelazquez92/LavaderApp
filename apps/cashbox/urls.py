# apps/cashbox/urls.py
from django.urls import path

from apps.cashbox import views

app_name = "cashbox"

urlpatterns = [
    path("", views.CashboxListView.as_view(), name="list"),
    path("abrir/", views.CashboxOpenView.as_view(), name="open"),
    path("<uuid:id>/cerrar/", views.CashboxCloseView.as_view(), name="close"),
    path("<uuid:id>/", views.CashboxDetailView.as_view(), name="detail"),
]
