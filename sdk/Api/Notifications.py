from __future__ import annotations

from notifications import Notification

from ._runtime import bind_window, call_window_method, get_window


def notify(*, title: str, message: str = "", duration_ms: int = 3500, app_id: str = "") -> None:
    call_window_method(
        "notify",
        title=title,
        message=message,
        duration_ms=duration_ms,
        app_id=app_id,
        required=True,
    )


def clear() -> None:
    window = get_window(required=True)
    notifications = getattr(window, "notifications", None)
    clear_method = getattr(notifications, "clear", None)
    if callable(clear_method):
        clear_method()
        return
    raise RuntimeError("Bound shell window does not expose notifications.clear().")


def set_dark_mode(dark_mode: bool) -> None:
    window = get_window(required=True)
    notifications = getattr(window, "notifications", None)
    setter = getattr(notifications, "set_dark_mode", None)
    if callable(setter):
        setter(bool(dark_mode))
        return
    raise RuntimeError("Bound shell window does not expose notifications.set_dark_mode().")


__all__ = [
    "Notification",
    "bind_window",
    "clear",
    "notify",
    "set_dark_mode",
]