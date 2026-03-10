from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.display")

@dataclass(frozen=True)
class DisplayInfo:
    brightness_percent: int | None = None
    auto_brightness: bool | None = None
    screen_on: bool | None = None
    driver: str = "unknown"


class DisplayDriverBase:
    def get_display_info(self) -> DisplayInfo:
        return DisplayInfo()

    def set_brightness(self, percent: int) -> bool:
        return False

    def set_auto_brightness(self, enabled: bool) -> bool:
        return False


_DISPLAY_DRIVER_LOCK = threading.Lock()
_DISPLAY_DRIVER: DisplayDriverBase | None = None
_DISPLAY_DRIVER_NAME: str | None = None


def set_display_driver(driver: DisplayDriverBase | None) -> None:
    global _DISPLAY_DRIVER, _DISPLAY_DRIVER_NAME
    with _DISPLAY_DRIVER_LOCK:
        _DISPLAY_DRIVER = driver
        _DISPLAY_DRIVER_NAME = None


def get_display_driver() -> DisplayDriverBase:
    global _DISPLAY_DRIVER, _DISPLAY_DRIVER_NAME

    chosen = str(get_device_driver_name("display", fallback="simulated")).strip().lower() or "simulated"
    with _DISPLAY_DRIVER_LOCK:
        if _DISPLAY_DRIVER is not None and _DISPLAY_DRIVER_NAME == chosen:
            return _DISPLAY_DRIVER

        _DISPLAY_DRIVER = _create_driver(chosen)
        _DISPLAY_DRIVER_NAME = chosen
        return _DISPLAY_DRIVER


def _create_driver(name: str) -> DisplayDriverBase:
    module_name = {
        "none": "drivers.display.none",
        "simulated": "drivers.display.simulated",
    }.get(str(name or "").strip().lower(), "drivers.display.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_display_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, DisplayDriverBase):
                return driver
    except Exception:
        pass

    return DisplayDriverBase()


def get_display_info() -> DisplayInfo:
    try:
        info = get_display_driver().get_display_info()
        return _normalize_info(info)
    except Exception:
        return DisplayInfo(driver="none")


def get_brightness() -> int | None:
    return get_display_info().brightness_percent


def set_brightness(percent: int) -> bool:
    try:
        value = max(0, min(100, int(percent)))
        return bool(get_display_driver().set_brightness(value))
    except Exception:
        return False


def set_auto_brightness(enabled: bool) -> bool:
    try:
        return bool(get_display_driver().set_auto_brightness(bool(enabled)))
    except Exception:
        return False


def _normalize_info(info: DisplayInfo | dict) -> DisplayInfo:
    if isinstance(info, dict):
        info = DisplayInfo(
            brightness_percent=info.get("brightness_percent"),
            auto_brightness=info.get("auto_brightness"),
            screen_on=info.get("screen_on"),
            driver=str(info.get("driver") or "unknown"),
        )

    brightness = info.brightness_percent
    if brightness is not None:
        brightness = max(0, min(100, int(brightness)))

    return DisplayInfo(
        brightness_percent=brightness,
        auto_brightness=(bool(info.auto_brightness) if info.auto_brightness is not None else None),
        screen_on=(bool(info.screen_on) if info.screen_on is not None else None),
        driver=str(info.driver or "unknown"),
    )
