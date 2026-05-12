from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import driver_config
from config import DeviceConfig, DeviceConfigStore
from driver_config import _default_driver, get_device_driver_name


class TestDriverConfig(unittest.TestCase):
    def test_default_driver_platforms(self) -> None:
        with patch("driver_config.os.name", "nt"), patch("driver_config.platform.system", return_value="Windows"):
            self.assertEqual(_default_driver("battery"), "winnt")
            self.assertEqual(_default_driver("wifi"), "netsh")

        with patch("driver_config.os.name", "posix"), patch("driver_config.platform.system", return_value="Linux"):
            self.assertEqual(_default_driver("battery"), "upower")
            self.assertEqual(_default_driver("audio"), "linux")
            self.assertEqual(_default_driver("thermals"), "vcgencmd")

    def test_get_device_driver_name_prefers_configured_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            DeviceConfigStore(base_dir=base_dir).save(DeviceConfig(drivers={"battery": "custom", "wifi": "wifi-driver"}))

            with patch.object(driver_config, "DeviceConfigStore") as store_cls:
                store_cls.return_value.load.return_value = DeviceConfig(drivers={"battery": "custom", "wifi": "wifi-driver"})
                self.assertEqual(get_device_driver_name("battery"), "custom")
                self.assertEqual(get_device_driver_name("wifi"), "wifi-driver")

    def test_get_device_driver_name_uses_legacy_and_fallback(self) -> None:
        legacy_config = type("LegacyConfig", (), {"drivers": {}, "battery_driver": "legacy-battery"})()
        with patch.object(driver_config, "DeviceConfigStore") as store_cls:
            store_cls.return_value.load.return_value = legacy_config
            self.assertEqual(get_device_driver_name("battery"), "legacy-battery")

        with patch.object(driver_config, "DeviceConfigStore") as store_cls:
            store_cls.return_value.load.side_effect = RuntimeError("boom")
            self.assertEqual(get_device_driver_name("battery", fallback="fallback"), "fallback")

    def test_get_device_driver_name_handles_empty_component(self) -> None:
        self.assertEqual(get_device_driver_name("", fallback="fallback"), "fallback")
        self.assertEqual(get_device_driver_name("   "), "none")


if __name__ == "__main__":
    unittest.main()