from __future__ import annotations

from wifi import WifiDriverBase, WifiInfo, WifiProfile
from logger import get_logger


log = get_logger("drivers.wifi.none")


class NoneWifiDriver(WifiDriverBase):
    def get_wifi_info(self) -> WifiInfo:
        log.debug("Wi-Fi none driver get_wifi_info requested")
        info = WifiInfo(enabled=False, connected=False, driver="none")
        log.debug("Wi-Fi none driver returning info", extra={"connected": info.connected})
        return info

    def scan_networks(self):
        log.debug("Wi-Fi none driver scan_networks requested")
        return []

    def list_profiles(self) -> list[WifiProfile]:
        log.debug("Wi-Fi none driver list_profiles requested")
        return []

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        log.info(
            "Wi-Fi none driver add_profile rejected",
            extra={"ssid": str(ssid or ""), "has_password": bool(password), "secure": secure},
        )
        return False

    def delete_profile(self, ssid: str) -> bool:
        log.info("Wi-Fi none driver delete_profile rejected", extra={"ssid": str(ssid or "")})
        return False


def create_wifi_driver() -> WifiDriverBase:
    log.info("Wi-Fi none driver created")
    return NoneWifiDriver()
