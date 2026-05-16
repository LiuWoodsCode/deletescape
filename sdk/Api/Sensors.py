from __future__ import annotations

from sensors import Vector3, SensorsInfo, get_sensors_info

from ._runtime import bind_window


def info() -> SensorsInfo:
    return get_sensors_info()


__all__ = [
    "Vector3",
    "SensorsInfo",
    "bind_window",
    "get_sensors_info",
    "info",
]
