from django.urls import path
from apps.cashbox import views

app_name = "cashbox"

urlpatterns = [
    path("", views.TurnoListView.as_view(), name="list"),
    path("abrir/", views.TurnoOpenView.as_view(), name="abrir"),
    path("<int:id>/cerrar/", views.TurnoCloseView.as_view(), name="cerrar"),
    path("<int:id>/", views.TurnoDetailView.as_view(), name="detalle"),
    path("z/", views.CierreZView.as_view(), name="z"),
]
