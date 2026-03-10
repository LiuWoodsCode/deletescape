from __future__ import annotations

import math
import importlib
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.location")

@dataclass(frozen=True)
class LocationInfo:
	"""Normalized best-effort location information.

	Notes on units:
	- latitude/longitude: decimal degrees
	- altitude_m: meters above sea level
	- accuracy_m: horizontal accuracy in meters
	- speed_mps: meters / second
	- heading_deg: 0..360 where 0 is north
	- timestamp_unix: UNIX seconds for when this reading was produced
	"""

	latitude: Optional[float] = None
	longitude: Optional[float] = None
	altitude_m: Optional[float] = None
	accuracy_m: Optional[float] = None
	speed_mps: Optional[float] = None
	heading_deg: Optional[float] = None
	timestamp_unix: Optional[float] = None

	provider: str = "unknown"


class LocationProviderBase:
	"""Minimal location provider interface for PhoneOS."""

	def get_location(self) -> LocationInfo:
		raise NotImplementedError


class SimulatedLocationProvider(LocationProviderBase):
	"""Development-friendly simulated location provider.

	The location drifts in a smooth loop around a center point so apps can
	observe movement without requiring hardware or OS permissions.
	"""

	def __init__(
		self,
		*,
		center_lat: float = 40.7128,
		center_lon: float = -74.0060,
		radius_m: float = 55.0,
		period_s: float = 120.0,
		altitude_m: float = 11.0,
		accuracy_m: float = 8.0,
	):
		self._center_lat = float(center_lat)
		self._center_lon = float(center_lon)
		self._radius_m = max(0.0, float(radius_m))
		self._period_s = max(15.0, float(period_s))
		self._altitude_m = float(altitude_m)
		self._accuracy_m = max(1.0, float(accuracy_m))
		self._seed = float(time.time() % self._period_s)

	def get_location(self) -> LocationInfo:
		now_mono = float(time.monotonic())
		angle = (2.0 * math.pi * (((now_mono + self._seed) % self._period_s) / self._period_s))

		meters_per_deg_lat = 111_320.0
		lat_rad = math.radians(self._center_lat)
		meters_per_deg_lon = max(1.0, 111_320.0 * math.cos(lat_rad))

		offset_north_m = self._radius_m * math.sin(angle)
		offset_east_m = self._radius_m * math.cos(angle)

		lat = self._center_lat + (offset_north_m / meters_per_deg_lat)
		lon = self._center_lon + (offset_east_m / meters_per_deg_lon)

		# Circle tangent heading: 0 north, 90 east, ...
		heading = math.degrees(angle + (math.pi / 2.0)) % 360.0

		# Approximate constant tangential speed for the circular motion.
		speed = (2.0 * math.pi * self._radius_m) / self._period_s if self._period_s > 0 else 0.0

		return LocationInfo(
			latitude=float(lat),
			longitude=float(lon),
			altitude_m=self._altitude_m,
			accuracy_m=self._accuracy_m,
			speed_mps=float(speed),
			heading_deg=float(heading),
			timestamp_unix=float(time.time()),
			provider="simulated",
		)


def _env_float(name: str) -> float | None:
	raw = os.environ.get(name)
	if raw is None:
		return None
	try:
		return float(raw.strip())
	except Exception:
		return None


def _build_default_provider() -> LocationProviderBase:
	"""Create the default provider.

	The initial implementation is simulated by design. Optional environment
	variables can pin the simulation center:
	- PHONEOS_GPS_LAT
	- PHONEOS_GPS_LON
	"""

	lat = _env_float("PHONEOS_GPS_LAT")
	lon = _env_float("PHONEOS_GPS_LON")

	if lat is None or lon is None:
		return SimulatedLocationProvider()

	return SimulatedLocationProvider(center_lat=lat, center_lon=lon)


_LOCATION_PROVIDER_LOCK = threading.Lock()
_LOCATION_PROVIDER: LocationProviderBase | None = None
_LOCATION_PROVIDER_DRIVER: str | None = None


def set_location_provider(provider: LocationProviderBase | None) -> None:
	"""Override the active provider.

	Passing None restores the default provider.
	"""

	global _LOCATION_PROVIDER
	global _LOCATION_PROVIDER_DRIVER
	with _LOCATION_PROVIDER_LOCK:
		_LOCATION_PROVIDER = provider
		_LOCATION_PROVIDER_DRIVER = None


def get_location_provider() -> LocationProviderBase:
	global _LOCATION_PROVIDER
	global _LOCATION_PROVIDER_DRIVER

	driver_name = str(get_device_driver_name("location", fallback="simulated")).strip().lower() or "simulated"

	with _LOCATION_PROVIDER_LOCK:
		if _LOCATION_PROVIDER is None or _LOCATION_PROVIDER_DRIVER != driver_name:
			_LOCATION_PROVIDER = _load_provider_from_driver(driver_name)
			_LOCATION_PROVIDER_DRIVER = driver_name
		return _LOCATION_PROVIDER


def _load_provider_from_driver(driver_name: str) -> LocationProviderBase:
	module_name = {
		"simulated": "drivers.location.simulated",
		"none": "drivers.location.none",
	}.get(str(driver_name or "").strip().lower(), "drivers.location.none")

	try:
		module = importlib.import_module(module_name)
		factory = getattr(module, "create_provider", None)
		if callable(factory):
			provider = factory()
			if isinstance(provider, LocationProviderBase):
				return provider
	except Exception:
		pass

	if driver_name == "simulated":
		return SimulatedLocationProvider()
	return _NoopLocationProvider()


class _NoopLocationProvider(LocationProviderBase):
	def get_location(self) -> LocationInfo:
		return LocationInfo(provider="none")


def _normalize(info: LocationInfo) -> LocationInfo:
	lat = info.latitude
	lon = info.longitude

	if lat is not None:
		lat = max(-90.0, min(90.0, float(lat)))
	if lon is not None:
		lon = max(-180.0, min(180.0, float(lon)))

	heading = info.heading_deg
	if heading is not None:
		heading = float(heading) % 360.0

	speed = info.speed_mps
	if speed is not None:
		speed = max(0.0, float(speed))

	accuracy = info.accuracy_m
	if accuracy is not None:
		accuracy = max(0.0, float(accuracy))

	ts = info.timestamp_unix if info.timestamp_unix is not None else float(time.time())

	return LocationInfo(
		latitude=lat,
		longitude=lon,
		altitude_m=(float(info.altitude_m) if info.altitude_m is not None else None),
		accuracy_m=accuracy,
		speed_mps=speed,
		heading_deg=heading,
		timestamp_unix=float(ts),
		provider=str(info.provider or "unknown"),
	)


def get_location_info() -> LocationInfo:
	"""Return the best-effort location from the active provider.

	Never raises; returns an empty/unknown LocationInfo on failure.
	"""

	try:
		provider = get_location_provider()
		info = provider.get_location()
		if isinstance(info, LocationInfo):
			return _normalize(info)
		if isinstance(info, dict):
			return _normalize(
				LocationInfo(
					latitude=info.get("latitude"),
					longitude=info.get("longitude"),
					altitude_m=info.get("altitude_m"),
					accuracy_m=info.get("accuracy_m"),
					speed_mps=info.get("speed_mps"),
					heading_deg=info.get("heading_deg"),
					timestamp_unix=info.get("timestamp_unix"),
					provider=str(info.get("provider") or "unknown"),
				)
			)
	except Exception:
		pass

	return _normalize(LocationInfo())


def has_location_fix(info: LocationInfo | None = None) -> bool:
	"""Return True if we have a usable latitude/longitude pair."""

	if info is None:
		info = get_location_info()
	return info.latitude is not None and info.longitude is not None
