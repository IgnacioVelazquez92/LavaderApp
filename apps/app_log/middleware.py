# apps/app_log/middleware.py
"""
Middlewares de observabilidad:

- RequestIDMiddleware: asigna un request_id único, gestiona parent_request_id en redirects
  y lo expone en header X-Request-ID.
- RequestLogMiddleware: registra cada request/response en AppLog (access log) y emite a log
  de archivos por usuario/día (logger 'apps.access'), incluyendo status, ms, redirect, mensajes y body_preview.
- AppLogExceptionMiddleware: captura excepciones no manejadas y las guarda en AppLog.
"""
import json
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.contrib.messages import get_messages

from .services.logger import log_event, log_exception, _request_context
from .utils import set_current_request, ensure_request_id, REQUEST_ID_HEADER

# Prefijos que no queremos loguear (static, media, admin assets, health checks)
SKIP_PREFIXES = (
    "/static/", "/media/", "/favicon.ico",
    "/admin/js/", "/admin/css/", "/admin/fonts/", "/healthz",
)

MAX_BODY_BYTES = 2048  # límite de captura de payload
SENSITIVE_KEYS = {"password", "token", "authorization",
                  "cookie", "secret", "apikey", "api_key"}


def _redact_dict(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        lk = str(k).lower()
        out[k] = "***redacted***" if any(
            s in lk for s in SENSITIVE_KEYS) else v
    return out


class RequestIDMiddleware(MiddlewareMixin):
    def process_request(self, request):
        set_current_request(request)
        ensure_request_id(request)
        parent = request.session.pop("_parent_request_id", None)
        setattr(request, "parent_request_id", parent)

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response[REQUEST_ID_HEADER] = str(rid)
        try:
            status = int(getattr(response, "status_code", 0))
            if 300 <= status < 400 and rid:
                request.session["_parent_request_id"] = str(rid)
        except Exception:
            pass
        return response


class RequestLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._app_log_started_at = time.perf_counter()

        # Captura segura de payload (solo POST/PUT/PATCH)
        request._app_log_body_preview = None
        try:
            if request.method in ("POST", "PUT", "PATCH"):
                ctype = request.META.get("CONTENT_TYPE", "")
                if "application/json" in ctype:
                    raw = request.body[:MAX_BODY_BYTES]
                    try:
                        data = json.loads(raw.decode("utf-8", errors="ignore"))
                        request._app_log_body_preview = _redact_dict(
                            data if isinstance(data, dict) else {}
                        )
                    except Exception:
                        request._app_log_body_preview = {
                            "_raw": raw.decode("utf-8", errors="ignore")
                        }
                elif "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
                    request._app_log_body_preview = _redact_dict(
                        request.POST.dict()
                    )
        except Exception:
            # No romper el request; mejor nada que tirar excepción en middleware
            pass

    def process_response(self, request, response):
        path = getattr(request, "path", "")
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        dur_ms = None
        if hasattr(request, "_app_log_started_at"):
            dur_ms = int(
                (time.perf_counter() - request._app_log_started_at) * 1000
            )

        status = getattr(response, "status_code", 0)
        level = "error" if status >= 500 else (
            "warning" if status >= 400 else "info"
        )

        redirect_to = getattr(response, "url", None) or getattr(
            getattr(response, "headers", None), "get", lambda *_: None
        )("Location")

        tmpl = getattr(response, "template_name", None)
        if hasattr(tmpl, "__iter__") and not isinstance(tmpl, (str, bytes)):
            try:
                template_name = ", ".join([str(t) for t in tmpl if t])
            except Exception:
                template_name = None
        else:
            template_name = str(tmpl) if tmpl else None

        # 👇 Captura de mensajes sin consumirlos definitivamente
        msgs = None
        try:
            storage = getattr(request, "_messages", None)
            if storage is not None:
                queued = list(getattr(storage, "_queued_messages", []) or [])
                loaded = list(getattr(storage, "_loaded_messages", []) or [])
                all_msgs = queued + loaded
                if all_msgs:
                    # Para el .log, serializamos a texto plano (evita __proxy__)
                    msgs = [{"level": m.level_tag,
                             "message": str(m)} for m in all_msgs]
        except Exception:
            msgs = None

        ctx = _request_context(request)
        meta = {
            **ctx,
            "status": status,
            "duration_ms": dur_ms,
            "route_name": getattr(getattr(request, "resolver_match", None), "view_name", None),
            "redirect_to": redirect_to,
            "messages": msgs or None,
            "template_name": template_name,
            "body_preview": getattr(request, "_app_log_body_preview", None),
        }

        # Guardar en BD
        log_event(
            level,
            origen="http",
            evento="access_log",
            mensaje=f"{getattr(request, 'method', '-') } {path}",
            meta=meta,
            request=request,
        )

        # Y a archivo (logger apps.access) con *todos* los extras
        logger = logging.getLogger("apps.access")
        logger.info(
            f"{getattr(request, 'method', '-') } {path}",
            extra={
                "status": status,
                "duration_ms": dur_ms,
                "redirect_to": redirect_to,
                "route_name": meta["route_name"],
                "template_name": template_name,
                "messages": msgs or None,
                "body_preview": getattr(request, "_app_log_body_preview", None),
            },
        )
        return response


class AppLogExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        log_exception("middleware", "unhandled_exception",
                      exception, request=request)
        return None
