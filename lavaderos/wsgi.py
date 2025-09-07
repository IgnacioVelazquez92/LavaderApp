import os
from django.core.wsgi import get_wsgi_application

# Obtenemos el valor de la variable de entorno DJANGO_ENV (puede ser: development, production, render)
# Si no está definida, por defecto será "development".
env = os.getenv("DJANGO_ENV", "development").strip().lower()

# Configuramos qué archivo de settings debe usar Django, según el valor anterior.
# Ejemplo: si DJANGO_ENV=production → lavaderos/settings/production.py
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"lavaderos.settings.{env}")

# Creamos la aplicación WSGI que servirá el proyecto en servidores web como Gunicorn o uWSGI.
application = get_wsgi_application()
