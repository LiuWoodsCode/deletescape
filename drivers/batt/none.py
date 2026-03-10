from __future__ import annotations

from battery import BatteryInfo
from logger import get_logger


log = get_logger("drivers.batt.none")


def read_battery_info() -> BatteryInfo:
    log.debug("Battery none driver read requested")
    info = BatteryInfo()
    log.debug(
        "Battery none driver returning empty info",
        extra={
            "percentage": info.percentage,
            "is_charging": info.is_charging,
        },
    )
    return info
