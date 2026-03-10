from __future__ import annotations

import math
import time

from battery import BatteryInfo
from logger import get_logger


_SEED = float(time.time())
log = get_logger("drivers.batt.simulated")


def read_battery_info() -> BatteryInfo:
    log.debug("Battery simulated driver read requested", extra={"seed": _SEED})
    t = float(time.monotonic())
    phase = ((t / 120.0) + (_SEED % 1.0)) * 2.0 * math.pi
    wave = 0.5 + 0.5 * math.sin(phase)
    pct = int(round(30 + wave * 65))
    pct = max(0, min(100, pct))
    info = BatteryInfo(percentage=pct, is_charging=False)
    log.debug(
        "Battery simulated driver returning info",
        extra={"time_monotonic": t, "phase": phase, "wave": wave, "percentage": pct},
    )
    return info
