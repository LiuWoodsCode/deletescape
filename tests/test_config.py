from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config as config_module
from config import (
    CONFIG_FILE_NAME,
    DEVICE_CONFIG_FILE_NAME,
    OS_BUILD_CONFIG_FILE_NAME,
    ConfigStore,
    DeviceConfig,
    DeviceConfigStore,
    OSBuildConfig,
    OSBuildConfigStore,
    OSConfig,
)


class TestOSConfig(unittest.TestCase):
    def test_round_trip(self) -> None:
        config = OSConfig(
            use_24h_time=False,
            dark_mode=True,
            lock_wallpaper="lock.png",
            home_wallpaper="home.png",
            setup_completed=True,
            embed_appid="app.home",
            kangel_enabled=True,
        )

        self.assertEqual(OSConfig.from_dict(config.to_dict(), default_kangel_enabled=False), config)

    def test_from_dict_uses_defaults(self) -> None:
        config = OSConfig.from_dict({}, default_kangel_enabled=True)

        self.assertTrue(config.use_24h_time)
        self.assertFalse(config.dark_mode)
        self.assertEqual(config.lock_wallpaper, "")
        self.assertEqual(config.home_wallpaper, "")
        self.assertFalse(config.setup_completed)
        self.assertTrue(config.kangel_enabled)
        self.assertEqual(config.embed_appid, "")


class TestOSBuildConfig(unittest.TestCase):
    def test_round_trip(self) -> None:
        config = OSBuildConfig(
            os_name="Deletescape",
            os_version="1.2.3",
            build_number=42,
            build_id="abc123",
            channel="dev",
            builder_username="builder",
            builder_hostname="host",
            build_datetime="2026-05-12T10:00:00Z",
        )

        self.assertEqual(OSBuildConfig.from_dict(config.to_dict()), config)

    def test_from_dict_coerces_values(self) -> None:
        config = OSBuildConfig.from_dict({"build_number": "7", "channel": 123})

        self.assertEqual(config.build_number, 7)
        self.assertEqual(config.channel, "123")


class TestConfigStores(unittest.TestCase):
    def test_config_store_load_save_and_dev_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            OSBuildConfigStore(base_dir=base_dir).save(OSBuildConfig(channel="dev"))

            store = ConfigStore(base_dir=base_dir)
            self.assertTrue(store.load().kangel_enabled)

            config = OSConfig(
                use_24h_time=False,
                dark_mode=True,
                lock_wallpaper="a",
                home_wallpaper="b",
                setup_completed=True,
                embed_appid="c",
                kangel_enabled=False,
            )
            store.save(config)

            written = json.loads((base_dir / CONFIG_FILE_NAME).read_text(encoding="utf-8"))
            self.assertEqual(written, config.to_dict())
            self.assertEqual(ConfigStore(base_dir=base_dir).load(), config)

    def test_device_config_from_dict_uses_host_defaults_and_driver_overrides(self) -> None:
        with patch("config.platform.system", return_value="Linux"), patch("config.platform.machine", return_value="x86_64"), patch(
            "config._get_host_device_defaults",
            return_value={
                "manufacturer": "HostCo",
                "model": "HostModel",
                "model_name": "HostModel",
                "serial_number": "SERIAL",
            },
        ):
            config = DeviceConfig.from_dict(
                {
                    "drivers": {"battery": "custom", "wifi": "wifi-driver"},
                    "audio_driver": "legacy-audio",
                    "has_hw_home": False,
                }
            )

        self.assertEqual(config.manufacturer, "HostCo")
        self.assertEqual(config.model, "generic_x86_64")
        self.assertEqual(config.model_name, "HostModel")
        self.assertEqual(config.serial_number, "SERIAL")
        self.assertFalse(config.has_hw_home)
        self.assertEqual(config.drivers["battery"], "custom")
        self.assertEqual(config.drivers["wifi"], "wifi-driver")
        self.assertEqual(config.drivers["audio"], "legacy-audio")

    def test_get_host_device_defaults_platform_variants(self) -> None:
        with patch("config.platform.system", return_value="Linux"), patch(
            "config._get_linux_hw",
            return_value={"manufacturer": "m", "model": "model", "serial": "s"},
        ):
            linux_defaults = config_module._get_host_device_defaults()

        with patch("config.platform.system", return_value="Windows"), patch(
            "config._get_windows_hw",
            return_value={"manufacturer": "wm", "model": "wmodel", "serial": "ws"},
        ):
            windows_defaults = config_module._get_host_device_defaults()

        self.assertEqual(linux_defaults["manufacturer"], "m")
        self.assertEqual(linux_defaults["model_name"], "model")
        self.assertEqual(windows_defaults["serial_number"], "ws")


if __name__ == "__main__":
    unittest.main()