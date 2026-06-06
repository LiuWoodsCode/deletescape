from __future__ import annotations

from display import (
    DisplayInfo,
    get_brightness,
    get_display_info,
    set_auto_brightness,
    set_brightness,
)

from ._runtime import bind_window


def info() -> DisplayInfo:
    return get_display_info()


__all__ = [
    "DisplayInfo",
    "bind_window",
    "get_brightness",
    "get_display_info",
    "info",
    "set_auto_brightness",
    "set_brightness",
]
