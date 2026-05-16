from __future__ import annotations

from vibration import VibrationInfo, get_vibration_info, stop_vibration, vibrate

from ._runtime import bind_window


def info() -> VibrationInfo:
    return get_vibration_info()


__all__ = [
    "VibrationInfo",
    "bind_window",
    "get_vibration_info",
    "info",
    "stop_vibration",
    "vibrate",
]
