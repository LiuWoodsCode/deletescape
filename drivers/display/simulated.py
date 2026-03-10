from __future__ import annotations

from display import DisplayDriverBase, DisplayInfo
from logger import get_logger


log = get_logger("drivers.display.simulated")


class SimulatedDisplayDriver(DisplayDriverBase):
    def __init__(self):
        self._brightness_percent = 72
        self._auto_brightness = False
        self._screen_on = True
        log.info("Simulated display driver initialized")

    def get_display_info(self) -> DisplayInfo:
        log.debug(
            "Simulated display get_display_info",
            extra={
                "brightness_percent": self._brightness_percent,
                "auto_brightness": self._auto_brightness,
                "screen_on": self._screen_on,
            },
        )
        return DisplayInfo(
            brightness_percent=self._brightness_percent,
            auto_brightness=self._auto_brightness,
            screen_on=self._screen_on,
            driver="simulated",
        )

    def set_brightness(self, percent: int) -> bool:
        self._brightness_percent = max(0, min(100, int(percent)))
        log.info("Simulated display brightness set", extra={"brightness_percent": self._brightness_percent})
        return True

    def set_auto_brightness(self, enabled: bool) -> bool:
        self._auto_brightness = bool(enabled)
        log.info("Simulated display auto brightness set", extra={"enabled": self._auto_brightness})
        return True


def create_display_driver() -> DisplayDriverBase:
    log.info("Creating simulated display driver")
    return SimulatedDisplayDriver()
