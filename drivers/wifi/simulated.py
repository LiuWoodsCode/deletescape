from __future__ import annotations

import math
import time

from wifi import WifiDriverBase, WifiInfo, WifiNetwork, WifiProfile
from logger import get_logger


log = get_logger("drivers.wifi.simulated")


class SimulatedWifiDriver(WifiDriverBase):
    def __init__(self):
        self._seed = float(time.time())
        self._ssid = "Home-5G"
        self._profiles: dict[str, WifiProfile] = {
            "Home-5G": WifiProfile(ssid="Home-5G", secure=True, source="simulated"),
            "CoffeeShop_WiFi": WifiProfile(ssid="CoffeeShop_WiFi", secure=False, source="simulated"),
        }
        log.info("Simulated Wi-Fi driver initialized", extra={"seed": self._seed, "ssid": self._ssid})

    def _signal(self) -> int:
        t = float(time.monotonic())
        x = (t / 25.0) + (self._seed % 1.0)
        wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * x)
        signal = max(20, min(100, int(round(45 + wave * 50))))
        log.debug("Simulated Wi-Fi signal sampled", extra={"t": t, "phase": x, "wave": wave, "signal": signal})
        return signal

    def get_wifi_info(self) -> WifiInfo:
        log.debug("Simulated Wi-Fi get_wifi_info requested")
        signal = self._signal()
        info = WifiInfo(
            enabled=True,
            connected=True,
            interface="wlan0",
            ssid=self._ssid,
            bssid="3C:28:6D:AA:BB:CC",
            ipv4="192.168.1.42",
            signal_percent=signal,
            rssi_dbm=-100 + int(signal * 0.5),
            mac_address="3C:28:6D:12:34:56",
            driver="simulated",
        )
        log.debug(
            "Simulated Wi-Fi info returned",
            extra={
                "ssid": info.ssid,
                "signal_percent": info.signal_percent,
                "rssi_dbm": info.rssi_dbm,
                "ipv4": info.ipv4,
            },
        )
        return info

    def scan_networks(self) -> list[WifiNetwork]:
        log.debug("Simulated Wi-Fi scan_networks requested")
        signal = self._signal()
        networks = [
            WifiNetwork(ssid=self._ssid, signal_percent=signal, secure=True, bssid="3C:28:6D:AA:BB:CC", frequency_mhz=5180.0, is_connected=True),
            WifiNetwork(ssid="CoffeeShop_WiFi", signal_percent=max(5, signal - 30), secure=False, bssid="10:22:33:44:55:66", frequency_mhz=2412.0, is_connected=False),
            WifiNetwork(ssid="Public_WiFi", signal_percent=max(5, signal - 45), secure=False, bssid="AA:BB:CC:DD:EE:FF", frequency_mhz=2437.0, is_connected=False),
        ]
        log.debug("Simulated Wi-Fi scan returned", extra={"count": len(networks)})
        return networks

    def list_profiles(self) -> list[WifiProfile]:
        profiles = list(self._profiles.values())
        log.debug("Simulated Wi-Fi list_profiles", extra={"count": len(profiles)})
        return profiles

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        clean = str(ssid or "").strip()
        if not clean:
            log.info("Simulated Wi-Fi add_profile rejected: empty ssid")
            return False
        if secure is None:
            secure = bool(password)
        self._profiles[clean] = WifiProfile(ssid=clean, secure=bool(secure), source="simulated")
        log.info(
            "Simulated Wi-Fi profile added",
            extra={"ssid": clean, "secure": bool(secure), "has_password": bool(password)},
        )
        return True

    def delete_profile(self, ssid: str) -> bool:
        clean = str(ssid or "").strip()
        if not clean:
            log.info("Simulated Wi-Fi delete_profile rejected: empty ssid")
            return False
        existed = clean in self._profiles
        self._profiles.pop(clean, None)
        log.info("Simulated Wi-Fi profile delete", extra={"ssid": clean, "deleted": existed})
        return bool(existed)


def create_wifi_driver() -> WifiDriverBase:
    log.info("Creating simulated Wi-Fi driver")
    return SimulatedWifiDriver()
