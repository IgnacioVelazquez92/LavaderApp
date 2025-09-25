# apps/org/urls.py
from django.urls import path
from . import views

app_name = "org"

urlpatterns = [
    path("empresas/", views.EmpresaListView.as_view(), name="empresas"),
    path("empresas/nueva/", views.EmpresaCreateView.as_view(), name="empresa_nueva"),
    path("empresas/<int:pk>/editar/",
         views.EmpresaUpdateView.as_view(), name="empresa_editar"),

    path("sucursales/", views.SucursalListView.as_view(), name="sucursales"),
    path("sucursales/nueva/", views.SucursalCreateView.as_view(),
         name="sucursal_nueva"),
    path("sucursales/<int:pk>/editar/",
         views.SucursalUpdateView.as_view(), name="sucursal_editar"),

    # ⬇️ Antes apuntaba a la FBV seleccionar_empresa (que ya no existe)
    path("seleccionar/", views.SelectorEmpresaView.as_view(), name="selector"),

    path("empleados/", views.EmpleadoListView.as_view(), name="empleados"),
    path("empleados/nuevo/", views.EmpleadoCreateView.as_view(),
         name="empleado_nuevo"),
    path("empleados/<int:pk>/editar/",
         views.EmpleadoUpdateView.as_view(), name="empleado_editar"),

    # Acciones sensibles: POST-only
    path("empleados/<int:pk>/reset-pass/",
         views.EmpleadoResetPasswordView.as_view(), name="empleado_reset_pass"),
    path("empleados/<int:pk>/toggle/",
         views.EmpleadoToggleActivoView.as_view(), name="empleado_toggle"),
    path("empleados/<int:pk>/eliminar/",
         views.EmpleadoDestroyUserView.as_view(), name="empleado_eliminar"),
]
