from __future__ import annotations

import re
import subprocess
import time

from logger import get_logger
from thermals import ThermalInfo, ThermalsDriverBase


log = get_logger("drivers.thermals.vcgencmd")
_TEMP_RE = re.compile(r"temp=([0-9]+(?:\.[0-9]+)?)")


class VcgencmdThermalsDriver(ThermalsDriverBase):
    def get_cpu_temperature(self) -> ThermalInfo:
        temp_c: float | None = None

        try:
            proc = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.returncode == 0:
                match = _TEMP_RE.search(str(proc.stdout or ""))
                if match is not None:
                    temp_c = float(match.group(1))
        except Exception:
            log.debug("vcgencmd measure_temp failed", exc_info=True)

        return ThermalInfo(
            cpu_temp_c=temp_c,
            timestamp_unix=float(time.time()),
            driver="vcgencmd",
        )


def create_thermals_driver() -> ThermalsDriverBase:
    log.info("Thermals vcgencmd driver created")
    return VcgencmdThermalsDriver()
