from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]  # o localhost/127.0.0.1

# DB simple (sqlite) para desarrollo
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Email a consola
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Archivos estáticos/media para dev
# (STATICFILES_DIRS ya está en base; no usar STATIC_ROOT en dev)
MEDIA_ROOT = BASE_DIR / "media"
