from __future__ import annotations

from typing import Callable

from background_tasks import BackgroundTaskHandle

from ._runtime import bind_window, call_window_method, get_window


def register(
    callback: Callable[[], None],
    *,
    interval_ms: int = 1000,
    name: str = "background_task",
    app_id: str | None = None,
    start_immediately: bool = False,
) -> BackgroundTaskHandle:
    return call_window_method(
        "register_background_task",
        callback,
        interval_ms=interval_ms,
        name=name,
        app_id=app_id,
        start_immediately=start_immediately,
        required=True,
    )


def enable(enabled: bool = True, *, app_id: str | None = None) -> None:
    call_window_method("enable_background", enabled, app_id=app_id, required=True)


def cancel(task_id: int) -> None:
    window = get_window(required=True)
    manager = getattr(window, "background_tasks", None)
    cancel_method = getattr(manager, "cancel", None)
    if callable(cancel_method):
        cancel_method(int(task_id))
        return
    raise RuntimeError("Bound shell window does not expose background_tasks.cancel().")


def cancel_for_app(app_id: str) -> None:
    window = get_window(required=True)
    manager = getattr(window, "background_tasks", None)
    cancel_method = getattr(manager, "cancel_for_app", None)
    if callable(cancel_method):
        cancel_method(str(app_id))
        return
    raise RuntimeError("Bound shell window does not expose background_tasks.cancel_for_app().")


def cancel_all() -> None:
    window = get_window(required=True)
    manager = getattr(window, "background_tasks", None)
    cancel_method = getattr(manager, "cancel_all", None)
    if callable(cancel_method):
        cancel_method()
        return
    raise RuntimeError("Bound shell window does not expose background_tasks.cancel_all().")


__all__ = [
    "BackgroundTaskHandle",
    "bind_window",
    "cancel",
    "cancel_all",
    "cancel_for_app",
    "enable",
    "register",
]