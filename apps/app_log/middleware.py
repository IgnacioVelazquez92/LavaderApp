# apps/app_log/middleware.py
"""
Middlewares de observabilidad:

- RequestIDMiddleware: asigna un request_id único y lo expone en header X-Request-ID.
- RequestLogMiddleware: registra cada request/response en AppLog (access log).
- AppLogExceptionMiddleware: captura excepciones no manejadas y las guarda en AppLog.
"""

import time
from django.utils.deprecation import MiddlewareMixin
from .services.logger import log_event, log_exception, _request_context
from .utils import set_current_request, ensure_request_id, REQUEST_ID_HEADER
import logging
# Prefijos que no queremos loguear (static, media, admin assets, health checks)
SKIP_PREFIXES = (
    "/static/", "/media/", "/favicon.ico",
    "/admin/js/", "/admin/css/", "/admin/fonts/", "/healthz",
)


class RequestIDMiddleware(MiddlewareMixin):
    """
    Middleware que asegura un request_id único por request
    y lo agrega en la respuesta como header X-Request-ID.
    """

    def process_request(self, request):
        set_current_request(request)
        ensure_request_id(request)

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response[REQUEST_ID_HEADER] = str(rid)
        return response


class RequestLogMiddleware(MiddlewareMixin):
    """
    Middleware que registra cada request/response en AppLog:
    - Método, path, status, duración, usuario, empresa, IP.
    - Clasifica el nivel según status (info, warning, error).
    """

    def process_request(self, request):
        request._app_log_started_at = time.perf_counter()

    def process_response(self, request, response):
        path = getattr(request, "path", "")
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        dur_ms = None
        if hasattr(request, "_app_log_started_at"):
            dur_ms = int(
                (time.perf_counter() - request._app_log_started_at) * 1000)

        status = getattr(response, "status_code", 0)
        level = "error" if status >= 500 else "warning" if status >= 400 else "info"

        ctx = _request_context(request)
        meta = {
            **ctx,
            "status": status,
            "duration_ms": dur_ms,
            "route_name": getattr(getattr(request, "resolver_match", None), "view_name", None),
        }

        log_event(
            level,
            origen="http",
            evento="access_log",
            mensaje=f"{request.method} {path}",
            meta=meta,
            request=request,
        )

        logger = logging.getLogger("apps.access")
        logger.info(
            f"{request.method} {path}",
            extra={
                "status": status,
                "duration_ms": dur_ms,
            },
        )
        return response

    def process_exception(self, request, exception):
        log_exception("http", "unhandled_exception",
                      exception, request=request)
        return None


class AppLogExceptionMiddleware(MiddlewareMixin):
    """
    Middleware de fallback para capturar excepciones no manejadas.
    Incluso si no pasa por RequestLogMiddleware, asegura que
    quede registrado en AppLog.
    """

    def process_exception(self, request, exception):
        log_exception("middleware", "unhandled_exception",
                      exception, request=request)
        return None
