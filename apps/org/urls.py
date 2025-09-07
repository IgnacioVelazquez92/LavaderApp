from django.urls import path
from .views import SelectorEmpresaView

urlpatterns = [
    path("org/seleccionar/", SelectorEmpresaView.as_view(), name="org_selector"),
]
