from django.contrib.messages import constants as messages
from pathlib import Path
import os

# -------------------------------------------------------------------
# BASE
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../project_root
DEBUG = False  # se sobreescribe en cada entorno
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "insecure-dev-key")  # prod: siempre por env

ALLOWED_HOSTS = []  # se sobreescribe por entorno

# -------------------------------------------------------------------
# APPS
# -------------------------------------------------------------------
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # Autenticación (allauth)
    "allauth",
    "allauth.account",
    # "allauth.socialaccount",  # no lo usamos por ahora

    # Apps del proyecto
    "apps.org",
    "apps.accounts",
    "apps.customers",
    "apps.vehicles",
    "apps.catalog",
]

SITE_ID = 1  # requerido por allauth

# -------------------------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "lavaderos.middleware.TenancyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lavaderos.urls"  # ajusta al nombre real de tu módulo de URLs raíz

# -------------------------------------------------------------------
# TEMPLATES
# -------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # overrides globales (account/, base.html, etc.)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",  # requerido por allauth
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.csrf",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -------------------------------------------------------------------
# AUTH / ALLAUTH (comunes)
# -------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Login solo por email (sin username)
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
# MVP; en prod real, podrías usar "mandatory"
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_USERNAME_REQUIRED = False

# Rutas de post-login/logout
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/"

# Permitir cerrar sesión con GET (sin página de confirmación)
ACCOUNT_LOGOUT_ON_GET = True

# Formularios personalizados (Bootstrap desde los forms)
ACCOUNT_FORMS = {
    "login": "apps.accounts.forms.LoginForm",
    "signup": "apps.accounts.forms.SignupForm",
    "reset_password": "apps.accounts.forms.ResetPasswordForm",              # ← nuevo
    "reset_password_from_key": "apps.accounts.forms.ResetPasswordKeyForm",  # ← nuevo
    "change_password": "apps.accounts.forms.ChangePasswordForm",            # ← opcional
}

# -------------------------------------------------------------------
# I18N / ZONA HORARIA
# -------------------------------------------------------------------
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Tucuman"
USE_I18N = True
USE_TZ = True

# -------------------------------------------------------------------
# STATIC & MEDIA
#   - STATIC_URL y MEDIA_* son comunes.
#   - En dev: podés usar STATICFILES_DIRS para /static/ local.
#   - En prod: se define STATIC_ROOT para collectstatic.
# -------------------------------------------------------------------
STATIC_URL = "/static/"
MEDIA_URL = "/media/"

# Solo si tenés una carpeta /static/ en el repo para assets de desarrollo:
STATICFILES_DIRS = [BASE_DIR / "static"]

# En prod se define: STATIC_ROOT = BASE_DIR / "staticfiles"
# y opcionalmente MEDIA_ROOT (si servís media desde disco)

# -------------------------------------------------------------------
# MENSAJES (Bootstrap friendly)
# -------------------------------------------------------------------
MESSAGE_TAGS = {
    messages.DEBUG: "secondary",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

# -------------------------------------------------------------------
# EMAIL (base)
#   - En dev: consola.
#   - En prod: SMTP real.
# -------------------------------------------------------------------
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "noreply@example.com")
EMAIL_SUBJECT_PREFIX = "[Lavadero] "

# Por defecto no fijamos backend aquí; cada entorno lo define.
# EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"         # prod
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"      # dev

# -------------------------------------------------------------------
# DB / CACHE / SEGURIDAD
#   - No se fijan en base.py para no acoplar entornos.
#   - Se definen en development.py / production.py
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# LOGGING (común y simple; ajustá según tus necesidades)
# -------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

SAAS_MAX_EMPRESAS_POR_USUARIO = 1
