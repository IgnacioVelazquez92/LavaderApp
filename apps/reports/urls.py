# apps/reports/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    # Vistas operativas
    path("sales/daily/", views.SalesDailyView.as_view(), name="sales_daily"),
    path("payments/method/", views.PaymentsByMethodView.as_view(),
         name="payments_by_method"),
    path("sales/shift/", views.SalesByShiftView.as_view(), name="sales_by_shift"),
    path("monthly/", views.MonthlyConsolidatedView.as_view(), name="monthly"),

    # Exportación
    path("export/", views.ExportReportView.as_view(), name="export"),
]
