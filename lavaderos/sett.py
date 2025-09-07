# lavaderos/settings/base.py
from pathlib import Path
import os

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]  # .../lavaderosApp

# Clave (se provee por .env en cualquier entorno)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")


# Apps
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",   # requerido por allauth

    # Autenticación
    "allauth",
    "allauth.account",
    "allauth.socialaccount",

    # Apps propias
    "apps.accounts",
    "apps.org",
    "apps.customers",
    "apps.vehicles",
    "apps.catalog",
    "apps.pricing",
    "apps.sales",
    "apps.payments",
    "apps.invoicing",
    "apps.notifications",
    "apps.cashbox",
    "apps.saas",
    "apps.audit",
    "apps.app_log",

]
SITE_ID = int(os.getenv("SITE_ID", "1"))

# Middlewares
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # <-- AÑADIR AQUÍ
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "lavaderos.urls"

# Templates (motor Django)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # <- tu carpeta global
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",  # <- requerido por allauth
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.csrf",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "lavaderos.wsgi.application"
ASGI_APPLICATION = "lavaderos.asgi.application"

# NO definir DATABASES acá (lo define cada entorno)

# Passwords (común)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# I18N/L10N (podés ajustar si querés es-AR/otra TZ)
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static/Media (común; collectstatic usará STATIC_ROOT en prod)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allauth (común)
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = os.getenv(
    "ACCOUNT_EMAIL_VERIFICATION", "none")  # prod puede forzar "mandatory"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_FORMS = {
    "login": "apps.accounts.forms.LoginForm",
    "signup": "apps.accounts.forms.SignupForm",
    # (más adelante: "reset_password", "change_password", etc.)
}

# NO definir EMAIL_BACKEND acá (cada entorno decide)
# Logging mínimo (común; se puede ampliar por entorno)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
