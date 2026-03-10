from __future__ import annotations

from display import DisplayDriverBase, DisplayInfo
from logger import get_logger


log = get_logger("drivers.display.none")


class NoneDisplayDriver(DisplayDriverBase):
    def get_display_info(self) -> DisplayInfo:
        log.debug("Display none driver get_display_info requested")
        return DisplayInfo(
            brightness_percent=None,
            auto_brightness=None,
            screen_on=None,
            driver="none",
        )

    def set_brightness(self, percent: int) -> bool:
        log.info("Display none driver set_brightness rejected", extra={"percent": int(percent)})
        return False

    def set_auto_brightness(self, enabled: bool) -> bool:
        log.info("Display none driver set_auto_brightness rejected", extra={"enabled": bool(enabled)})
        return False


def create_display_driver() -> DisplayDriverBase:
    log.info("Display none driver created")
    return NoneDisplayDriver()
