from __future__ import annotations

import math
import time

from logger import get_logger
from thermals import ThermalInfo, ThermalsDriverBase


_SEED = float(time.time())
log = get_logger("drivers.thermals.simulated")


class SimulatedThermalsDriver(ThermalsDriverBase):
    def get_cpu_temperature(self) -> ThermalInfo:
        t = float(time.monotonic())
        phase = ((t / 90.0) + (_SEED % 1.0)) * 2.0 * math.pi
        wave = 0.5 + 0.5 * math.sin(phase)
        temp_c = round(68.0 + (wave * 24.0), 2)
        log.debug(
            "Thermals simulated driver returning info",
            extra={"time_monotonic": t, "phase": phase, "cpu_temp_c": temp_c},
        )
        return ThermalInfo(
            cpu_temp_c=temp_c,
            timestamp_unix=float(time.time()),
            driver="simulated",
        )


def create_thermals_driver() -> ThermalsDriverBase:
    log.info("Thermals simulated driver created", extra={"seed": _SEED})
    return SimulatedThermalsDriver()
