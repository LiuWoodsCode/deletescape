from __future__ import annotations

from location import LocationInfo, LocationProviderBase
from logger import get_logger


log = get_logger("drivers.location.none")


class NullLocationProvider(LocationProviderBase):
    def get_location(self) -> LocationInfo:
        log.debug("Location none driver get_location requested")
        info = LocationInfo(provider="none")
        log.debug("Location none driver returning empty fix")
        return info


def create_provider() -> LocationProviderBase:
    log.info("Location none driver provider created")
    return NullLocationProvider()
