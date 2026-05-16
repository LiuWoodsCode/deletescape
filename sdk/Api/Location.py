from __future__ import annotations

from location import LocationInfo, SimulatedLocationProvider, get_location_info, get_location_provider, has_location_fix, set_location_provider

from ._runtime import bind_window


def info() -> LocationInfo:
    return get_location_info()


__all__ = [
    "LocationInfo",
    "SimulatedLocationProvider",
    "bind_window",
    "get_location_info",
    "get_location_provider",
    "has_location_fix",
    "info",
    "set_location_provider",
]
