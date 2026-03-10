from __future__ import annotations

from vibration import VibrationDriverBase, VibrationInfo
from logger import get_logger


log = get_logger("drivers.vibration.none")


class NoneVibrationDriver(VibrationDriverBase):
    def get_vibration_info(self) -> VibrationInfo:
        log.debug("Vibration none driver get_vibration_info requested")
        return VibrationInfo(
            supported=False,
            haptics_supported=False,
            max_intensity=None,
            driver="none",
        )

    def vibrate(self, duration_ms: int, *, intensity: float | None = None) -> bool:
        log.info(
            "Vibration none driver vibrate rejected",
            extra={"duration_ms": int(duration_ms), "intensity": intensity},
        )
        return False

    def stop(self) -> bool:
        log.debug("Vibration none driver stop requested")
        return False


def create_vibration_driver() -> VibrationDriverBase:
    log.info("Vibration none driver created")
    return NoneVibrationDriver()
