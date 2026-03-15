from __future__ import annotations

import time

from logger import get_logger
from thermals import ThermalInfo, ThermalsDriverBase


log = get_logger("drivers.thermals.none")


class NoneThermalsDriver(ThermalsDriverBase):
    def get_cpu_temperature(self) -> ThermalInfo:
        log.debug("Thermals none driver read requested")
        return ThermalInfo(
            cpu_temp_c=None,
            timestamp_unix=float(time.time()),
            driver="none",
        )


def create_thermals_driver() -> ThermalsDriverBase:
    log.info("Thermals none driver created")
    return NoneThermalsDriver()
