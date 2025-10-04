from typing import Tuple
from django.core.mail.backends.smtp import EmailBackend
from ..models import EmailServer


def build_backend_from_emailserver(srv: EmailServer) -> EmailBackend:
    """
    Construye un EmailBackend de Django configurado con los datos del EmailServer.
    """
    return EmailBackend(
        host=srv.host,
        port=srv.port,
        username=srv.username or None,
        password=srv.get_password() or None,
        use_tls=srv.use_tls,
        use_ssl=srv.use_ssl,
        timeout=15,
        fail_silently=False,
    )


def test_smtp_connection(srv: EmailServer) -> Tuple[bool, str | None]:
    """
    Intenta abrir y cerrar conexión con el servidor SMTP.
    Retorna (True, None) si fue exitoso.
    Retorna (False, error) si hubo problema.
    """
    try:
        backend = build_backend_from_emailserver(srv)
        if hasattr(backend, "open"):
            backend.open()
            backend.close()
        return True, None
    except Exception as e:
        return False, str(e)
