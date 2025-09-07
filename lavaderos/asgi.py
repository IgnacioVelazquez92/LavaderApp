import os
from django.core.asgi import get_asgi_application

# tomamos el entorno de ejecución.
env = os.getenv("DJANGO_ENV", "development").strip().lower()

# Seleccionamos el módulo de configuración adecuado de Django según el entorno.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"lavaderos.settings.{env}")

# Creamos la aplicación ASGI que servirá el proyecto en servidores que soportan async,
# como Daphne, Uvicorn o Hypercorn (útil para websockets, etc.).
application = get_asgi_application()
