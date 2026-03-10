from __future__ import annotations

import os

from location import SimulatedLocationProvider, LocationProviderBase
from logger import get_logger


log = get_logger("drivers.location.simulated")


def _env_float(name: str) -> float | None:
    value = os.environ.get(name)
    log.debug("Location simulated env read", extra={"name": name, "present": value is not None})
    if value is None:
        return None
    try:
        parsed = float(value.strip())
        log.debug("Location simulated env parsed", extra={"name": name, "value": parsed})
        return parsed
    except Exception:
        log.warning("Location simulated env parse failed", extra={"name": name, "raw": str(value)})
        return None


def create_provider() -> LocationProviderBase:
    log.info("Creating simulated location provider")
    lat = _env_float("PHONEOS_GPS_LAT")
    lon = _env_float("PHONEOS_GPS_LON")

    if lat is None or lon is None:
        log.debug("Using default simulated center (no env override)")
        return SimulatedLocationProvider()

    log.debug("Using env-based simulated center", extra={"lat": lat, "lon": lon})
    return SimulatedLocationProvider(center_lat=lat, center_lon=lon)
