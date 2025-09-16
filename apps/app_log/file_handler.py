# apps/app_log/file_handler.py
"""
Handler que escribe un .log por USUARIO y por DÍA (YYYY-MM-DD/username.log).
Usa el request actual desde thread-local (utils.get_current_request).

⚠️ Privacidad: no escribas PII sensible en los logs si no es necesario.
"""

import os
import logging
import datetime
import re
from typing import Optional
from .utils import get_current_request


def _sanitize_filename(name: str) -> str:
    # Solo letras, números, guiones y guion_bajo
    name = name.lower().strip() or "anon"
    return re.sub(r"[^a-z0-9_-]+", "-", name)


class PerUserDailyFileHandler(logging.Handler):
    """
    Crea/usa archivos:
        <BASE_DIR>/<YYYY-MM-DD>/<username>.log
    Si no hay usuario autenticado -> "anon.log".
    """

    def __init__(self, base_dir: str = "logs", encoding: str = "utf-8", level=logging.NOTSET):
        super().__init__(level)
        self.base_dir = base_dir
        self.encoding = encoding
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_path(self) -> str:
        today = datetime.date.today().isoformat()  # YYYY-MM-DD
        req = get_current_request()
        if req and getattr(req, "user", None) and getattr(req.user, "is_authenticated", False):
            username = getattr(req.user, "username", "") or str(
                getattr(req.user, "id", "")) or "user"
        else:
            username = "anon"
        username = _sanitize_filename(username)
        day_dir = os.path.join(self.base_dir, today)
        os.makedirs(day_dir, exist_ok=True)
        return os.path.join(day_dir, f"{username}.log")

    def emit(self, record: logging.LogRecord):
        try:
            # usa el formatter definido en settings.LOGGING
            msg = self.format(record)
            path = self._resolve_path()
            with open(path, "a", encoding=self.encoding, newline="\n") as f:
                f.write(msg + "\n")
        except Exception:
            # Nunca interrumpir logging
            pass
