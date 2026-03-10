from __future__ import annotations

from vibration import VibrationDriverBase, VibrationInfo
from logger import get_logger


log = get_logger("drivers.vibration.simulated")


class SimulatedVibrationDriver(VibrationDriverBase):
    def __init__(self):
        self._active = False
        self._last_duration_ms = 0
        self._last_intensity = 0.8
        log.info("Simulated vibration driver initialized")

    def get_vibration_info(self) -> VibrationInfo:
        return VibrationInfo(
            supported=True,
            haptics_supported=True,
            max_intensity=1.0,
            driver="simulated",
        )

    def vibrate(self, duration_ms: int, *, intensity: float | None = None) -> bool:
        self._active = True
        self._last_duration_ms = max(1, int(duration_ms))
        self._last_intensity = 0.8 if intensity is None else max(0.0, min(1.0, float(intensity)))
        log.info(
            "Simulated vibration started",
            extra={
                "duration_ms": self._last_duration_ms,
                "intensity": self._last_intensity,
            },
        )
        return True

    def stop(self) -> bool:
        was_active = self._active
        self._active = False
        log.info("Simulated vibration stopped", extra={"was_active": was_active})
        return bool(was_active)


def create_vibration_driver() -> VibrationDriverBase:
    log.info("Creating simulated vibration driver")
    return SimulatedVibrationDriver()
