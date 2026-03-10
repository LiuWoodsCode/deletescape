from __future__ import annotations

import time

from sensors import SensorsDriverBase, SensorsInfo
from logger import get_logger


log = get_logger("drivers.sensors.none")


class NoneSensorsDriver(SensorsDriverBase):
    def get_sensors_info(self) -> SensorsInfo:
        log.debug("Sensors none driver get_sensors_info requested")
        return SensorsInfo(
            timestamp_unix=float(time.time()),
            driver="none",
        )


def create_sensors_driver() -> SensorsDriverBase:
    log.info("Sensors none driver created")
    return NoneSensorsDriver()
