from __future__ import annotations

from wifi import (
    WifiInfo,
    WifiNetwork,
    WifiProfile,
    add_wifi_profile,
    delete_wifi_profile,
    get_wifi_info,
    list_wifi_profiles,
    scan_wifi_networks,
)

from ._runtime import bind_window


def info() -> WifiInfo:
    return get_wifi_info()


def get_info() -> WifiInfo:
    return get_wifi_info()


def scan() -> list[WifiNetwork]:
    return scan_wifi_networks()


def list_profiles() -> list[WifiProfile]:
    return list_wifi_profiles()


def add_profile(ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
    return add_wifi_profile(ssid, password=password, secure=secure)


def delete_profile(ssid: str) -> bool:
    return delete_wifi_profile(ssid)


__all__ = [
    "WifiInfo",
    "WifiNetwork",
    "WifiProfile",
    "bind_window",
    "add_profile",
    "add_wifi_profile",
    "delete_profile",
    "delete_wifi_profile",
    "get_info",
    "get_wifi_info",
    "info",
    "list_profiles",
    "list_wifi_profiles",
    "scan",
    "scan_wifi_networks",
]