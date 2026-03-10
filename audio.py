from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.audio")

@dataclass(frozen=True)
class AudioInfo:
    volume_percent: int | None = None
    muted: bool | None = None
    output_route: str | None = None
    driver: str = "unknown"


class AudioDriverBase:
    def get_audio_info(self) -> AudioInfo:
        return AudioInfo()

    def set_volume(self, percent: int) -> bool:
        return False

    def set_muted(self, muted: bool) -> bool:
        return False


_AUDIO_DRIVER_LOCK = threading.Lock()
_AUDIO_DRIVER: AudioDriverBase | None = None
_AUDIO_DRIVER_NAME: str | None = None


def set_audio_driver(driver: AudioDriverBase | None) -> None:
    global _AUDIO_DRIVER, _AUDIO_DRIVER_NAME
    with _AUDIO_DRIVER_LOCK:
        _AUDIO_DRIVER = driver
        _AUDIO_DRIVER_NAME = None


def get_audio_driver() -> AudioDriverBase:
    global _AUDIO_DRIVER, _AUDIO_DRIVER_NAME

    chosen = str(get_device_driver_name("audio", fallback="simulated")).strip().lower() or "simulated"
    with _AUDIO_DRIVER_LOCK:
        if _AUDIO_DRIVER is not None and _AUDIO_DRIVER_NAME == chosen:
            return _AUDIO_DRIVER

        _AUDIO_DRIVER = _create_driver(chosen)
        _AUDIO_DRIVER_NAME = chosen
        return _AUDIO_DRIVER


def _create_driver(name: str) -> AudioDriverBase:
    module_name = {
        "none": "drivers.audio.none",
        "simulated": "drivers.audio.simulated",
    }.get(str(name or "").strip().lower(), "drivers.audio.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_audio_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, AudioDriverBase):
                return driver
    except Exception:
        pass

    return AudioDriverBase()


def get_audio_info() -> AudioInfo:
    try:
        info = get_audio_driver().get_audio_info()
        return _normalize_info(info)
    except Exception:
        return AudioInfo(driver="none")


def get_volume() -> int | None:
    return get_audio_info().volume_percent


def set_volume(percent: int) -> bool:
    try:
        value = max(0, min(100, int(percent)))
        return bool(get_audio_driver().set_volume(value))
    except Exception:
        return False


def set_muted(muted: bool) -> bool:
    try:
        return bool(get_audio_driver().set_muted(bool(muted)))
    except Exception:
        return False


def _normalize_info(info: AudioInfo | dict) -> AudioInfo:
    if isinstance(info, dict):
        info = AudioInfo(
            volume_percent=info.get("volume_percent"),
            muted=info.get("muted"),
            output_route=info.get("output_route"),
            driver=str(info.get("driver") or "unknown"),
        )

    volume = info.volume_percent
    if volume is not None:
        volume = max(0, min(100, int(volume)))

    return AudioInfo(
        volume_percent=volume,
        muted=(bool(info.muted) if info.muted is not None else None),
        output_route=(str(info.output_route) if info.output_route else None),
        driver=str(info.driver or "unknown"),
    )
