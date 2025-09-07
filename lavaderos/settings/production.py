from .base import *
import dj_database_url  # si usás DATABASE_URL

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(
    ",")  # ej: "miapp.com,.onrender.com"

# DB real (Postgres)
DATABASES = {
    "default": dj_database_url.config(conn_max_age=600, ssl_require=True)
}

# Email real (SMTP)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True

# Staticfiles para collectstatic
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

# Si tenés dominio/s en https:
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "").split(",") if origin]

# Seguridad web recomendada (activable por env)
SECURE_SSL_REDIRECT = os.getenv(
    "SECURE_SSL_REDIRECT", "true").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv(
    "SESSION_COOKIE_SECURE", "true").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "true").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
SECURE_HSTS_PRELOAD = os.getenv(
    "SECURE_HSTS_PRELOAD", "true").lower() == "true"
