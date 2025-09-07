from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.org.urls")),
    path("", TemplateView.as_view(template_name="marketing/home.html"), name="home"),
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
