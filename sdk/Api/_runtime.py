from __future__ import annotations

from typing import Any


_CURRENT_WINDOW: Any | None = None
_BOUND_APP_ID: str | None = None


def bind_window(window: Any | None, *, app_id: str | None = None) -> None:
    """Bind the host window and (optionally) the authoritative app id.

    The host should call `bind_window(window, app_id=...)` when launching an
    app so the SDK can inject the trusted `app_id` into any window method
    calls that accept an `app_id` parameter. Callers should NOT attempt to
    set `app_id` themselves; any `app_id` passed to API functions will be
    overridden by the bound value.
    """
    global _CURRENT_WINDOW, _BOUND_APP_ID
    _CURRENT_WINDOW = window
    _BOUND_APP_ID = None if app_id is None else str(app_id)


def get_window(*, required: bool = False) -> Any | None:
    window = _CURRENT_WINDOW
    if window is not None:
        return window

    if required:
        raise RuntimeError("No shell window is bound. Call sdk.bind_window(window, app_id=...) first.")

    return None


def get_bound_app_id() -> str | None:
    return _BOUND_APP_ID


def call_window_method(
    method_name: str,
    *args: Any,
    required: bool = False,
    default: Any = None,
    **kwargs: Any,
) -> Any:
    """Call a method on the bound host window.

    If an app is bound via `bind_window(..., app_id=...)`, any `app_id`
    provided in `kwargs` will be ignored and replaced with the bound value
    to prevent apps from spoofing their identity.
    """
    # Inject or override `app_id` from the bound context to prevent spoofing.
    bound_app = _BOUND_APP_ID
    if "app_id" in kwargs:
        # Always override any supplied app_id with the bound value (which may be None).
        kwargs["app_id"] = bound_app
    else:
        if bound_app is not None:
            kwargs["app_id"] = bound_app

    window = get_window(required=required)
    if window is None:
        return default

    method = getattr(window, str(method_name), None)
    if not callable(method):
        if required:
            raise RuntimeError(f"Bound shell window does not implement {method_name}().")
        return default

    return method(*args, **kwargs)