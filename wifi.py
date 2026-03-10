from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading
from typing import Optional

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.wifi")

@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal_percent: Optional[int] = None
    secure: Optional[bool] = None
    bssid: Optional[str] = None
    frequency_mhz: Optional[float] = None
    is_connected: bool = False


@dataclass(frozen=True)
class WifiInfo:
    enabled: Optional[bool] = None
    connected: Optional[bool] = None
    interface: Optional[str] = None
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    ipv4: Optional[str] = None
    signal_percent: Optional[int] = None
    rssi_dbm: Optional[int] = None
    mac_address: Optional[str] = None
    driver: str = "unknown"

@dataclass(frozen=True)
class WifiProfile:
    ssid: str
    secure: Optional[bool] = None
    source: Optional[str] = None


class WifiDriverBase:
    def get_wifi_info(self) -> WifiInfo:
        return WifiInfo()

    def scan_networks(self) -> list[WifiNetwork]:
        return []

    def list_profiles(self) -> list[WifiProfile]:
        return []

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        return False

    def delete_profile(self, ssid: str) -> bool:
        return False


_WIFI_DRIVER_LOCK = threading.Lock()
_WIFI_DRIVER: WifiDriverBase | None = None
_WIFI_DRIVER_NAME: str | None = None


def set_wifi_driver(driver: WifiDriverBase | None) -> None:
    global _WIFI_DRIVER, _WIFI_DRIVER_NAME
    with _WIFI_DRIVER_LOCK:
        _WIFI_DRIVER = driver
        _WIFI_DRIVER_NAME = None


def get_wifi_driver() -> WifiDriverBase:
    global _WIFI_DRIVER, _WIFI_DRIVER_NAME

    chosen = str(get_device_driver_name("wifi", fallback="netsh")).strip().lower() or "netsh"
    with _WIFI_DRIVER_LOCK:
        if _WIFI_DRIVER is not None and _WIFI_DRIVER_NAME == chosen:
            return _WIFI_DRIVER

        _WIFI_DRIVER = _create_driver(chosen)
        _WIFI_DRIVER_NAME = chosen
        return _WIFI_DRIVER


def _create_driver(name: str) -> WifiDriverBase:
    module_name = {
        "none": "drivers.wifi.none",
        "simulated": "drivers.wifi.simulated",
        "netsh": "drivers.wifi.netsh",
        "nmcli": "drivers.wifi.nmcli",
        "iwctl": "drivers.wifi.iwctl",
    }.get(str(name or "").strip().lower(), "drivers.wifi.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_wifi_driver", None)
        if callable(factory):
            driver = factory()
            if isinstance(driver, WifiDriverBase):
                return driver
    except Exception:
        pass

    return WifiDriverBase()


def get_wifi_info() -> WifiInfo:
    try:
        info = get_wifi_driver().get_wifi_info()
        return _normalize_info(info)
    except Exception:
        return WifiInfo(driver="none")


def scan_wifi_networks() -> list[WifiNetwork]:
    try:
        nets = get_wifi_driver().scan_networks()
        return [_normalize_network(n) for n in list(nets or [])]
    except Exception:
        return []


def list_wifi_profiles() -> list[WifiProfile]:
    try:
        profiles = get_wifi_driver().list_profiles()
        return [_normalize_profile(p) for p in list(profiles or [])]
    except Exception:
        return []


def add_wifi_profile(ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
    try:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            return False
        return bool(get_wifi_driver().add_profile(clean_ssid, password=password, secure=secure))
    except Exception:
        return False


def delete_wifi_profile(ssid: str) -> bool:
    try:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            return False
        return bool(get_wifi_driver().delete_profile(clean_ssid))
    except Exception:
        return False


def _normalize_info(info: WifiInfo | dict) -> WifiInfo:
    if isinstance(info, dict):
        info = WifiInfo(
            enabled=info.get("enabled"),
            connected=info.get("connected"),
            interface=info.get("interface"),
            ssid=info.get("ssid"),
            bssid=info.get("bssid"),
            ipv4=info.get("ipv4"),
            signal_percent=info.get("signal_percent"),
            rssi_dbm=info.get("rssi_dbm"),
            mac_address=info.get("mac_address"),
            driver=str(info.get("driver") or "unknown"),
        )

    signal = info.signal_percent
    if signal is not None:
        signal = max(0, min(100, int(signal)))

    rssi = info.rssi_dbm
    if rssi is not None:
        rssi = int(rssi)

    return WifiInfo(
        enabled=(bool(info.enabled) if info.enabled is not None else None),
        connected=(bool(info.connected) if info.connected is not None else None),
        interface=(str(info.interface) if info.interface else None),
        ssid=(str(info.ssid) if info.ssid else None),
        bssid=(str(info.bssid) if info.bssid else None),
        ipv4=(str(info.ipv4) if info.ipv4 else None),
        signal_percent=signal,
        rssi_dbm=rssi,
        mac_address=(str(info.mac_address) if info.mac_address else None),
        driver=str(info.driver or "unknown"),
    )


def _normalize_network(network: WifiNetwork | dict) -> WifiNetwork:
    if isinstance(network, dict):
        network = WifiNetwork(
            ssid=str(network.get("ssid") or ""),
            signal_percent=network.get("signal_percent"),
            secure=network.get("secure"),
            bssid=network.get("bssid"),
            frequency_mhz=network.get("frequency_mhz"),
            is_connected=bool(network.get("is_connected", False)),
        )

    signal = network.signal_percent
    if signal is not None:
        signal = max(0, min(100, int(signal)))

    return WifiNetwork(
        ssid=str(network.ssid or ""),
        signal_percent=signal,
        secure=(bool(network.secure) if network.secure is not None else None),
        bssid=(str(network.bssid) if network.bssid else None),
        frequency_mhz=(float(network.frequency_mhz) if network.frequency_mhz is not None else None),
        is_connected=bool(network.is_connected),
    )


def _normalize_profile(profile: WifiProfile | dict) -> WifiProfile:
    if isinstance(profile, dict):
        profile = WifiProfile(
            ssid=str(profile.get("ssid") or ""),
            secure=profile.get("secure"),
            source=profile.get("source"),
        )

    return WifiProfile(
        ssid=str(profile.ssid or ""),
        secure=(bool(profile.secure) if profile.secure is not None else None),
        source=(str(profile.source) if profile.source else None),
    )
