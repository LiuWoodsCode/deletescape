from __future__ import annotations

import os
import platform
from typing import Any
import traceback
from config import DeviceConfigStore

from logger import PROCESS_START, get_logger
log = get_logger("drvconfig")

def _default_driver(component: str) -> str:
    comp = str(component or "").strip().lower()
    if comp == "battery":
        return "winnt" if os.name == "nt" else "upower"
    if comp == "modem":
        return "none"
    if comp == "location":
        return "none"
    if comp == "wifi":
        return "netsh" if os.name == "nt" else "nmcli"
    if comp == "display":
        return "none"
    if comp == "audio":
        return "none"
    if comp == "sensors":
        return "none"
    if comp == "thermals":
        return "vcgencmd" if platform.system() == "Linux" else "none"
    if comp == "vibration":
        return "none"
    return "none"


def get_device_driver_name(component: str, *, fallback: str | None = None) -> str:
    """Return configured driver name for a device component.

    Reads from `deviceconfig.json` using key `drivers.<component>`.
    Also supports legacy flat keys (`battery_driver`, `modem_driver`, `location_driver`).
    """

    comp = str(component or "").strip().lower()
    if not comp:
        return str(fallback or "none")

    chosen_fallback = str(fallback or _default_driver(comp)).strip().lower() or "none"

    try:
        cfg = DeviceConfigStore().load()
    except Exception:
        return chosen_fallback

    try:
        drivers = getattr(cfg, "drivers", None)
        if isinstance(drivers, dict):
            value = drivers.get(comp)
            if value is not None:
                name = str(value).strip().lower()
                if name:
                    return name
    except Exception:
        pass

    try:
        legacy = getattr(cfg, f"{comp}_driver", None)
        if legacy is not None:
            name = str(legacy).strip().lower()
            if name:
                return name
    except Exception:
        pass

    return chosen_fallback
