from __future__ import annotations

from battery import BatteryInfo
from logger import get_logger


log = get_logger("drivers.batt.psutil")

def read_battery_info() -> BatteryInfo:
    log.debug("Battery psutil driver read requested")
    import psutil  # type: ignore

    battery = psutil.sensors_battery()
    log.debug("psutil.sensors_battery result", extra={"is_none": battery is None})
    if battery is None or battery.percent is None:
        log.info("Battery psutil driver found no battery data")
        return None

    info = BatteryInfo(
        percentage=int(round(float(battery.percent))),
        is_charging=bool(getattr(battery, "power_plugged", False)),
    )
    log.debug(
        "Battery psutil driver returning info",
        extra={
            "percentage": info.percentage,
            "is_charging": info.is_charging,
            "secsleft": getattr(battery, "secsleft", None),
        },
    )
    return info
