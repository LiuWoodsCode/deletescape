from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading
import time

from driver_config import get_device_driver_name

from logger import get_logger


log = get_logger("hal.thermals")


@dataclass(frozen=True)
class ThermalInfo:
    cpu_temp_c: float | None = None
    timestamp_unix: float | None = None
    driver: str = "unknown"


class ThermalsDriverBase:
    def get_cpu_temperature(self) -> ThermalInfo:
        return ThermalInfo(timestamp_unix=float(time.time()), driver="none")


_THERMALS_DRIVER_LOCK = threading.Lock()
_THERMALS_DRIVER: ThermalsDriverBase | None = None
_THERMALS_DRIVER_NAME: str | None = None


def set_thermals_driver(driver: ThermalsDriverBase | None) -> None:
    global _THERMALS_DRIVER, _THERMALS_DRIVER_NAME
    with _THERMALS_DRIVER_LOCK:
        _THERMALS_DRIVER = driver
        _THERMALS_DRIVER_NAME = None


def get_thermals_driver() -> ThermalsDriverBase:
    global _THERMALS_DRIVER, _THERMALS_DRIVER_NAME

    chosen = str(get_device_driver_name("thermals", fallback="none")).strip().lower() or "none"
    with _THERMALS_DRIVER_LOCK:
        if _THERMALS_DRIVER is not None and _THERMALS_DRIVER_NAME == chosen:
            return _THERMALS_DRIVER

        _THERMALS_DRIVER = _create_driver(chosen)
        _THERMALS_DRIVER_NAME = chosen
        return _THERMALS_DRIVER


def _create_driver(name: str) -> ThermalsDriverBase:
    module_name = {
        "none": "drivers.thermals.none",
        "simulated": "drivers.thermals.simulated",
        "vcgencmd": "drivers.thermals.vcgencmd",
    }.get(str(name or "").strip().lower(), "drivers.thermals.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_thermals_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, ThermalsDriverBase):
                return driver
    except Exception:
        log.exception("Failed to create thermals driver", extra={"module_name": module_name})

    return ThermalsDriverBase()


def get_thermal_info() -> ThermalInfo:
    try:
        info = get_thermals_driver().get_cpu_temperature()
        return _normalize(info)
    except Exception:
        return ThermalInfo(timestamp_unix=float(time.time()), driver="none")


def get_cpu_temperature_c() -> float | None:
    return get_thermal_info().cpu_temp_c


def _normalize(info: ThermalInfo | dict | float | int | None) -> ThermalInfo:
    if info is None:
        return ThermalInfo(timestamp_unix=float(time.time()), driver="none")

    if isinstance(info, (float, int)):
        return ThermalInfo(
            cpu_temp_c=float(info),
            timestamp_unix=float(time.time()),
            driver="unknown",
        )

    if isinstance(info, dict):
        info = ThermalInfo(
            cpu_temp_c=(float(info.get("cpu_temp_c")) if info.get("cpu_temp_c") is not None else None),
            timestamp_unix=(float(info.get("timestamp_unix")) if info.get("timestamp_unix") is not None else None),
            driver=str(info.get("driver") or "unknown"),
        )

    temp = info.cpu_temp_c
    if temp is not None:
        temp = float(temp)

    ts = float(info.timestamp_unix) if info.timestamp_unix is not None else float(time.time())
    return ThermalInfo(
        cpu_temp_c=temp,
        timestamp_unix=ts,
        driver=str(info.driver or "unknown"),
    )
