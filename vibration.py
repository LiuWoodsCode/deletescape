from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.vibration")

@dataclass(frozen=True)
class VibrationInfo:
    supported: bool = False
    haptics_supported: bool = False
    max_intensity: float | None = None
    driver: str = "unknown"


class VibrationDriverBase:
    def get_vibration_info(self) -> VibrationInfo:
        return VibrationInfo()

    def vibrate(self, duration_ms: int, *, intensity: float | None = None) -> bool:
        return False

    def stop(self) -> bool:
        return False


_VIBRATION_DRIVER_LOCK = threading.Lock()
_VIBRATION_DRIVER: VibrationDriverBase | None = None
_VIBRATION_DRIVER_NAME: str | None = None


def set_vibration_driver(driver: VibrationDriverBase | None) -> None:
    global _VIBRATION_DRIVER, _VIBRATION_DRIVER_NAME
    with _VIBRATION_DRIVER_LOCK:
        _VIBRATION_DRIVER = driver
        _VIBRATION_DRIVER_NAME = None


def get_vibration_driver() -> VibrationDriverBase:
    global _VIBRATION_DRIVER, _VIBRATION_DRIVER_NAME

    chosen = str(get_device_driver_name("vibration", fallback="simulated")).strip().lower() or "simulated"
    with _VIBRATION_DRIVER_LOCK:
        if _VIBRATION_DRIVER is not None and _VIBRATION_DRIVER_NAME == chosen:
            return _VIBRATION_DRIVER

        _VIBRATION_DRIVER = _create_driver(chosen)
        _VIBRATION_DRIVER_NAME = chosen
        return _VIBRATION_DRIVER


def _create_driver(name: str) -> VibrationDriverBase:
    module_name = {
        "none": "drivers.vibration.none",
        "simulated": "drivers.vibration.simulated",
    }.get(str(name or "").strip().lower(), "drivers.vibration.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_vibration_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, VibrationDriverBase):
                return driver
    except Exception:
        pass

    return VibrationDriverBase()


def get_vibration_info() -> VibrationInfo:
    try:
        info = get_vibration_driver().get_vibration_info()
        return _normalize_info(info)
    except Exception:
        return VibrationInfo(driver="none")


def vibrate(duration_ms: int, *, intensity: float | None = None) -> bool:
    try:
        log.debug(f"Buzz! (for {duration_ms} ms)")
        duration = max(1, int(duration_ms))
        value = None if intensity is None else max(0.0, min(1.0, float(intensity)))
        return bool(get_vibration_driver().vibrate(duration, intensity=value))
    except Exception:
        return False


def stop_vibration() -> bool:
    try:
        return bool(get_vibration_driver().stop())
    except Exception:
        return False


def _normalize_info(info: VibrationInfo | dict) -> VibrationInfo:
    if isinstance(info, dict):
        info = VibrationInfo(
            supported=bool(info.get("supported", False)),
            haptics_supported=bool(info.get("haptics_supported", False)),
            max_intensity=(
                float(info.get("max_intensity"))
                if info.get("max_intensity") is not None
                else None
            ),
            driver=str(info.get("driver") or "unknown"),
        )

    max_intensity = info.max_intensity
    if max_intensity is not None:
        max_intensity = max(0.0, min(1.0, float(max_intensity)))

    return VibrationInfo(
        supported=bool(info.supported),
        haptics_supported=bool(info.haptics_supported),
        max_intensity=max_intensity,
        driver=str(info.driver or "unknown"),
    )
