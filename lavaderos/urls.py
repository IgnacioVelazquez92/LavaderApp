from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from apps.org.views import PostLoginRedirectView, DashboardView
from django.contrib.auth.decorators import login_required
from apps.saas.selectors import planes_activos
from django.views.generic import TemplateView
from django.shortcuts import render


def public_home_view(request):
    # Si ya está logueado, no tiene sentido mostrar la pública
    if request.user.is_authenticated:
        return redirect("home")
    planes = planes_activos()
    return render(request, "home_public.html", {"planes": planes})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.accounts.urls")),
    path("public/", public_home_view, name="public_home"),

    # apps
    path("org/", include("apps.org.urls")),
    path("clientes/", include("apps.customers.urls", namespace="customers")),
    path("vehiculos/", include("apps.vehicles.urls", namespace="vehicles")),
    path("catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("precios/", include("apps.pricing.urls", namespace="pricing")),
    path("ventas/", include("apps.sales.urls", namespace="sales")),
    path("", include(("apps.payments.urls", "payments"), namespace="payments")),
    path("", include(("apps.invoicing.urls", "invoicing"), namespace="invoicing")),
    path(
        "notificaciones/",
        include(("apps.notifications.urls", "notifications"),
                namespace="notifications"),
    ),
    path("saas/", include("apps.saas.urls", namespace="saas")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    path("", login_required(DashboardView.as_view(
        template_name="home_dashboard.html")), name="home"),

    path("caja/", include(("apps.cashbox.urls", "cashbox"), namespace="cashbox")),

    path("post-login/", PostLoginRedirectView.as_view(), name="post_login"),
]

# archivos de media en dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)

# handlers de errores (templates/errors/*.html)
handler401 = "django.views.defaults.permission_denied"
handler403 = "django.views.defaults.permission_denied"
handler404 = "django.views.defaults.page_not_found"
handler500 = "django.views.defaults.server_error"
