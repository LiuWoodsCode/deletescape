from __future__ import annotations

from battery import BatteryInfo, get_battery_info

from ._runtime import bind_window


def info() -> BatteryInfo:
    return get_battery_info()


def get_info() -> BatteryInfo:
    return get_battery_info()


__all__ = [
    "BatteryInfo",
    "bind_window",
    "get_info",
    "get_battery_info",
    "info",
]
