from __future__ import annotations

import math
import time

from sensors import SensorsDriverBase, SensorsInfo, Vector3
from logger import get_logger


log = get_logger("drivers.sensors.simulated")


class SimulatedSensorsDriver(SensorsDriverBase):
    def __init__(self):
        self._seed = float(time.time())
        log.info("Simulated sensors driver initialized", extra={"seed": self._seed})

    def get_sensors_info(self) -> SensorsInfo:
        t = float(time.monotonic())
        phase = (t / 5.0) + (self._seed % 1.0)

        accel = Vector3(
            x=round(0.08 * math.sin(phase), 4),
            y=round(0.08 * math.cos(phase * 0.9), 4),
            z=round(9.81 + 0.04 * math.sin(phase * 0.7), 4),
        )
        gyro = Vector3(
            x=round(2.1 * math.sin(phase * 1.3), 4),
            y=round(1.7 * math.cos(phase * 1.1), 4),
            z=round(1.2 * math.sin(phase * 0.8), 4),
        )
        magnet = Vector3(
            x=round(25.0 + 6.0 * math.sin(phase * 0.3), 4),
            y=round(-3.0 + 4.0 * math.cos(phase * 0.35), 4),
            z=round(38.0 + 3.0 * math.sin(phase * 0.25), 4),
        )

        ambient = max(0.0, 240.0 + 210.0 * math.sin((t / 18.0) + (self._seed % 0.7)))
        barometer = 1013.25 + 1.7 * math.sin((t / 40.0) + (self._seed % 0.5))

        info = SensorsInfo(
            accelerometer=accel,
            gyroscope=gyro,
            magnetometer=magnet,
            ambient_light_lux=round(float(ambient), 3),
            barometer_hpa=round(float(barometer), 3),
            timestamp_unix=float(time.time()),
            driver="simulated",
        )
        log.debug(
            "Simulated sensors sample",
            extra={
                "accel": {"x": info.accelerometer.x, "y": info.accelerometer.y, "z": info.accelerometer.z},
                "gyro": {"x": info.gyroscope.x, "y": info.gyroscope.y, "z": info.gyroscope.z},
                "mag": {"x": info.magnetometer.x, "y": info.magnetometer.y, "z": info.magnetometer.z},
                "ambient_light_lux": info.ambient_light_lux,
                "barometer_hpa": info.barometer_hpa,
            },
        )
        return info


def create_sensors_driver() -> SensorsDriverBase:
    log.info("Creating simulated sensors driver")
    return SimulatedSensorsDriver()
