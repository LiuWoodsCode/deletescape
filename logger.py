from __future__ import annotations

import datetime as _dt
import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from datetime import datetime

date_str = datetime.now().strftime("%Y-%m-%d")
_DEFAULT_LOG_FILE = f"logs/deletescape_{date_str}.log"

# Best-effort "process start" marker for startup timing.
# This is set at first import of `logger`, which happens very early in boot.
PROCESS_START = time.perf_counter()


class _IsoFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        # ISO-ish local timestamp with milliseconds.
        dt = _dt.datetime.fromtimestamp(record.created)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)

        # Include any structured fields passed via `extra={...}`.
        # Python logging stores these directly on the LogRecord instance.
        try:
            extras = _extract_extras(record)
            if not extras:
                return base
            return base + " (" + _format_kv(extras) + ")"
        except Exception:
            return base


_configured = False


_STANDARD_RECORD_ATTRS = {
    # Core LogRecord fields
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        try:
            return f"<{type(value).__name__}>"
        except Exception:
            return "<unreprable>"


def _format_kv(d: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in sorted(d.keys()):
        parts.append(f"{k}={_safe_repr(d[k])}")
    return " ".join(parts)


def _extract_extras(record: logging.LogRecord) -> dict[str, Any]:
    raw = getattr(record, "__dict__", {})
    extras: dict[str, Any] = {}
    for k, v in raw.items():
        if k in _STANDARD_RECORD_ATTRS:
            continue
        # Avoid dumping private/dunder fields.
        if k.startswith("_"):
            continue
        extras[str(k)] = v
    return extras


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def configure(
    *,
    level: str | int = "INFO",
    log_to_file: bool = True,
    log_file: str | os.PathLike[str] | None = None,
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> None:
    """Configure root logging for the whole OS.

    Safe to call multiple times; subsequent calls are no-ops.
    """

    global _configured
    if _configured:
        return

    # Allow environment overrides.
    env_level = os.environ.get("DELETESCAPE_LOG_LEVEL")
    if env_level:
        level = env_level

    env_log_to_file = os.environ.get("DELETESCAPE_LOG_TO_FILE")
    if env_log_to_file:
        log_to_file = _truthy(env_log_to_file)

    env_log_file = os.environ.get("DELETESCAPE_LOG_FILE")
    if env_log_file:
        log_file = env_log_file

    root = logging.getLogger()
    root.setLevel(level)

    fmt = (
        "%(asctime)s %(name)s[%(process)d:%(thread)d] "
        "%(levelname)s %(message)s"
    )
    formatter = _IsoFormatter(fmt=fmt)

    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setLevel(level)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_to_file:
        try:
            path = Path(log_file or _DEFAULT_LOG_FILE)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent / path
            path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                filename=str(path),
                maxBytes=int(max_bytes),
                backupCount=int(backup_count),
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except Exception:
            # Never fail startup due to logging.
            pass

    # Make sure unhandled thread exceptions show up even if app_health hooks are not installed.
    _install_thread_excepthook_fallback()

    _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or "Deletescape")


def log_exception(logger: logging.Logger, message: str, *, exc_info=True, **extra: Any) -> None:
    try:
        if extra:
            message = message + " | " + " ".join(f"{k}={v!r}" for k, v in extra.items())
        logger.exception(message, exc_info=exc_info)
    except Exception:
        # Last resort fallback.
        try:
            print(message)
        except Exception:
            pass


def _install_thread_excepthook_fallback() -> None:
    if not hasattr(threading, "excepthook"):
        return

    previous = threading.excepthook

    def _hook(args):
        try:
            get_logger("thread").exception(
                "Unhandled exception in thread",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        except Exception:
            pass
        try:
            previous(args)
        except Exception:
            pass

    threading.excepthook = _hook


def install_qt_message_handler() -> None:
    """Route Qt internal warnings/info to Python logging when possible."""

    try:
        from PySide6.QtCore import qInstallMessageHandler  # type: ignore
        from PySide6.QtCore import QtMsgType  # type: ignore
    except Exception:
        return

    log = get_logger("qt")

    def _handler(mode, context, message):
        try:
            msg = str(message)
            if context is not None:
                try:
                    # context: file, line, function
                    file = getattr(context, "file", "") or ""
                    line = getattr(context, "line", 0) or 0
                    function = getattr(context, "function", "") or ""
                    if file or function or line:
                        msg = f"{msg} | qt={file}:{line} {function}".strip()
                except Exception:
                    pass

            if mode == QtMsgType.QtDebugMsg:
                log.debug(msg)
            elif mode == QtMsgType.QtInfoMsg:
                log.info(msg)
            elif mode == QtMsgType.QtWarningMsg:
                log.warning(msg)
            elif mode == QtMsgType.QtCriticalMsg:
                log.error(msg)
            elif mode == QtMsgType.QtFatalMsg:
                log.critical(msg)
            else:
                log.info(msg)
        except Exception:
            pass

    try:
        qInstallMessageHandler(_handler)
    except Exception:
        pass
