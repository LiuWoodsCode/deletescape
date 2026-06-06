from __future__ import annotations

from pathlib import Path

from config import (
    ConfigStore,
    DeviceConfig,
    DeviceConfigStore,
    OSBuildConfig,
    OSBuildConfigStore,
    OSConfig,
)

from ._runtime import bind_window


def load() -> OSConfig:
    return ConfigStore().load()


def load_device_config() -> DeviceConfig:
    return DeviceConfigStore().load()


def load_os_build() -> OSBuildConfig:
    return OSBuildConfigStore().load()


__all__ = [
    "ConfigStore",
    "DeviceConfig",
    "DeviceConfigStore",
    "OSBuildConfig",
    "OSBuildConfigStore",
    "OSConfig",
    "bind_window",
    "load",
    "load_device_config",
    "load_os_build",
]
