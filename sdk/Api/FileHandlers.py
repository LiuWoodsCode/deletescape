from __future__ import annotations

from pathlib import Path

from file_handlers import (
    get_handlers_for_path,
    register_handler,
    unregister_handler,
    open_with_app as _open_with_app,
)

from ._runtime import bind_window, get_window


def handlers_for_path(path: str | Path) -> list[dict]:
    return get_handlers_for_path(Path(path))


def open_with_app(app_id: str, path: str | Path) -> None:
    window = get_window(required=True)
    _open_with_app(window, str(app_id), Path(path))


__all__ = [
    "bind_window",
    "get_handlers_for_path",
    "handlers_for_path",
    "open_with_app",
    "register_handler",
    "unregister_handler",
]
