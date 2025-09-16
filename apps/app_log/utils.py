# apps/app_log/utils.py
"""
Utilidades para manejo de contexto en logs:
- Guardar el request actual en un thread-local.
- Generar y asegurar un request_id único por cada request.
- Recuperar request actual desde cualquier parte del código (ej. en signals).
"""

import threading
import uuid
from typing import Optional
from django.http import HttpRequest

# Thread-local para almacenar el request actual
_local = threading.local()

# Nombre del header estándar que usamos para correlación
REQUEST_ID_HEADER = "X-Request-ID"


def set_current_request(request: Optional[HttpRequest]):
    """
    Guarda el request actual en el contexto local del thread.

    Usado desde middleware al inicio de cada request.
    """
    _local.request = request


def get_current_request() -> Optional[HttpRequest]:
    """
    Recupera el request actual almacenado en thread-local.
    Devuelve None si no existe.
    """
    return getattr(_local, "request", None)


def ensure_request_id(request: HttpRequest) -> uuid.UUID:
    """
    Asegura que el request tenga un request_id (UUID).
    - Si ya existe, lo devuelve.
    - Si no, genera uno nuevo y lo asigna al request.
    """
    rid = getattr(request, "request_id", None)
    if not rid:
        rid = uuid.uuid4()
        request.request_id = rid
    return rid
