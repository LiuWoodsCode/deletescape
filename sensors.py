from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading
import time

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.sensors")

@dataclass(frozen=True)
class Vector3:
    x: float | None = None
    y: float | None = None
    z: float | None = None


@dataclass(frozen=True)
class SensorsInfo:
    accelerometer: Vector3 = Vector3()
    gyroscope: Vector3 = Vector3()
    magnetometer: Vector3 = Vector3()
    ambient_light_lux: float | None = None
    barometer_hpa: float | None = None
    timestamp_unix: float | None = None
    driver: str = "unknown"

class SensorsDriverBase:
    def get_sensors_info(self) -> SensorsInfo:
        return SensorsInfo()


_SENSORS_DRIVER_LOCK = threading.Lock()
_SENSORS_DRIVER: SensorsDriverBase | None = None
_SENSORS_DRIVER_NAME: str | None = None


def set_sensors_driver(driver: SensorsDriverBase | None) -> None:
    global _SENSORS_DRIVER, _SENSORS_DRIVER_NAME
    with _SENSORS_DRIVER_LOCK:
        _SENSORS_DRIVER = driver
        _SENSORS_DRIVER_NAME = None


def get_sensors_driver() -> SensorsDriverBase:
    global _SENSORS_DRIVER, _SENSORS_DRIVER_NAME

    chosen = str(get_device_driver_name("sensors", fallback="simulated")).strip().lower() or "simulated"
    with _SENSORS_DRIVER_LOCK:
        if _SENSORS_DRIVER is not None and _SENSORS_DRIVER_NAME == chosen:
            return _SENSORS_DRIVER

        _SENSORS_DRIVER = _create_driver(chosen)
        _SENSORS_DRIVER_NAME = chosen
        return _SENSORS_DRIVER


def _create_driver(name: str) -> SensorsDriverBase:
    module_name = {
        "none": "drivers.sensors.none",
        "simulated": "drivers.sensors.simulated",
    }.get(str(name or "").strip().lower(), "drivers.sensors.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_sensors_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, SensorsDriverBase):
                return driver
    except Exception:
        pass

    return SensorsDriverBase()


def get_sensors_info() -> SensorsInfo:
    try:
        info = get_sensors_driver().get_sensors_info()
        return _normalize(info)
    except Exception:
        return SensorsInfo(driver="none", timestamp_unix=float(time.time()))


def _normalize_vector(v: Vector3 | dict | None) -> Vector3:
    if v is None:
        return Vector3()
    if isinstance(v, dict):
        return Vector3(
            x=(float(v.get("x")) if v.get("x") is not None else None),
            y=(float(v.get("y")) if v.get("y") is not None else None),
            z=(float(v.get("z")) if v.get("z") is not None else None),
        )
    return Vector3(
        x=(float(v.x) if v.x is not None else None),
        y=(float(v.y) if v.y is not None else None),
        z=(float(v.z) if v.z is not None else None),
    )


def _normalize(info: SensorsInfo | dict) -> SensorsInfo:
    if isinstance(info, dict):
        info = SensorsInfo(
            accelerometer=info.get("accelerometer") if info.get("accelerometer") is not None else Vector3(),
            gyroscope=info.get("gyroscope") if info.get("gyroscope") is not None else Vector3(),
            magnetometer=info.get("magnetometer") if info.get("magnetometer") is not None else Vector3(),
            ambient_light_lux=info.get("ambient_light_lux"),
            barometer_hpa=info.get("barometer_hpa"),
            timestamp_unix=info.get("timestamp_unix"),
            driver=str(info.get("driver") or "unknown"),
        )

    ambient_light = info.ambient_light_lux
    if ambient_light is not None:
        ambient_light = max(0.0, float(ambient_light))

    barometer = info.barometer_hpa
    if barometer is not None:
        barometer = max(0.0, float(barometer))

    ts = float(info.timestamp_unix) if info.timestamp_unix is not None else float(time.time())

    return SensorsInfo(
        accelerometer=_normalize_vector(info.accelerometer),
        gyroscope=_normalize_vector(info.gyroscope),
        magnetometer=_normalize_vector(info.magnetometer),
        ambient_light_lux=ambient_light,
        barometer_hpa=barometer,
        timestamp_unix=ts,
        driver=str(info.driver or "unknown"),
    )
