import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
import subprocess
import platform

CONFIG_FILE_NAME = "config.json"
DEVICE_CONFIG_FILE_NAME = "deviceconfig.json"
OS_BUILD_CONFIG_FILE_NAME = "osconfig.json"


@dataclass
class OSConfig:
    use_24h_time: bool = True
    dark_mode: bool = False
    lock_wallpaper: str = ""
    home_wallpaper: str = ""
    setup_completed: bool = False
    kangel_enabled: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, default_kangel_enabled: bool = False) -> "OSConfig":
        return cls(
            use_24h_time=bool(data.get("use_24h_time", True)),
            dark_mode=bool(data.get("dark_mode", False)),
            lock_wallpaper=str(data.get("lock_wallpaper", "") or ""),
            home_wallpaper=str(data.get("home_wallpaper", "") or ""),
            setup_completed=bool(data.get("setup_completed", False)),
            kangel_enabled=bool(data.get("kangel_enabled", default_kangel_enabled)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "use_24h_time": self.use_24h_time,
            "dark_mode": self.dark_mode,
            "lock_wallpaper": self.lock_wallpaper,
            "home_wallpaper": self.home_wallpaper,
            "setup_completed": bool(self.setup_completed),
            "kangel_enabled": bool(self.kangel_enabled),
        }


class ConfigStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.path = self.base_dir / CONFIG_FILE_NAME

    def _default_kangel_enabled(self) -> bool:
        try:
            build = OSBuildConfigStore(base_dir=self.base_dir).load()
            return str(getattr(build, "channel", "")).strip().lower() == "dev"
        except Exception:
            return False

    def load(self) -> OSConfig:
        default_kangel_enabled = self._default_kangel_enabled()
        if not self.path.exists():
            return OSConfig(kangel_enabled=default_kangel_enabled)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return OSConfig.from_dict(data, default_kangel_enabled=default_kangel_enabled)
        except Exception:
            pass
        return OSConfig(kangel_enabled=default_kangel_enabled)

    def save(self, config: OSConfig) -> None:
        self.path.write_text(
            json.dumps(config.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def _get_windows_hw() -> dict:
    try:
        import wmi

        c = wmi.WMI()

        cs = c.Win32_ComputerSystem()[0]
        bios = c.Win32_BIOS()[0]

        manufacturer = (cs.Manufacturer or "").strip()
        model = (cs.Model or "").strip()
        serial = (bios.SerialNumber or "").strip()

        return {
            "manufacturer": manufacturer,
            "model": model,
            "serial": serial,
        }

    except Exception:
        return {
            "manufacturer": "",
            "model": "",
            "serial": "",
        }


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except Exception:
        return ""


def _get_linux_hw() -> dict:
    return {
        "manufacturer": _read_file("/sys/class/dmi/id/sys_vendor"),
        "model": _read_file("/sys/class/dmi/id/product_name"),
        "serial": _read_file("/sys/class/dmi/id/product_serial"),
    }


def _get_macos_hw() -> dict:
    serial = _run(["ioreg", "-l"])
    model = _run(["sysctl", "-n", "hw.model"])

    sn = ""
    for line in serial.splitlines():
        if "IOPlatformSerialNumber" in line:
            sn = line.split("=")[-1].replace('"', '').strip()

    return {
        "manufacturer": "Apple",
        "model": model,
        "serial": sn,
    }


def _get_host_device_defaults() -> dict:
    system = platform.system()

    if system == "Windows":
        hw = _get_windows_hw()
    elif system == "Linux":
        hw = _get_linux_hw()
    elif system == "Darwin":
        hw = _get_macos_hw()
    else:
        hw = {}

    model = hw.get("model", "") or ""

    return {
        "manufacturer": hw.get("manufacturer", "") or "",
        "model": model,
        "model_name": model,
        "serial_number": hw.get("serial", "") or "",
    }

@dataclass
class DeviceConfig:
    manufacturer: str = ""
    model: str = ""
    model_name: str = ""
    serial_number: str = ""
    hardware_revision: str = ""
    imei: str = ""
    wifi_mac: str = ""
    bluetooth_mac: str = ""
    has_hw_home: bool = False
    drivers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceConfig":
        def _get_str(key: str) -> str:
            value = data.get(key, "")
            return value if isinstance(value, str) else str(value)

        default_battery_driver = "winnt" if os.name == "nt" else "psinfo"
        default_wifi_driver = "netsh" if os.name == "nt" else "nmcli"
        default_thermals_driver = "vcgencmd" if platform.system() == "Linux" else "none"
        default_drivers: Dict[str, str] = {
            "battery": default_battery_driver,
            "modem": "none",
            "location": "none",
            "wifi": default_wifi_driver,
            "display": "none",
            "audio": "none",
            "sensors": "none",
            "thermals": default_thermals_driver,
            "vibration": "none",
        }

        parsed_drivers = dict(default_drivers)
        raw_drivers = data.get("drivers")
        if isinstance(raw_drivers, dict):
            for key, value in raw_drivers.items():
                k = str(key or "").strip().lower()
                v = str(value or "").strip().lower()
                if k and v:
                    parsed_drivers[k] = v

        for comp in ("battery", "modem", "location", "wifi", "display", "audio", "sensors", "thermals", "vibration"):
            legacy_value = data.get(f"{comp}_driver")
            if legacy_value is None:
                continue
            val = str(legacy_value or "").strip().lower()
            if val:
                parsed_drivers[comp] = val

        host_defaults = _get_host_device_defaults()

        manufacturer = _get_str("manufacturer") or host_defaults["manufacturer"]
        model = _get_str("model") or f"generic_{platform.machine()}"
        model_name = _get_str("model_name") or host_defaults["model_name"] or model
        serial_number = _get_str("serial_number") or host_defaults["serial_number"]

        return cls(
            manufacturer=manufacturer,
            model=model,
            model_name=model_name,
            serial_number=serial_number,
            hardware_revision=_get_str("hardware_revision"),
            imei=_get_str("imei"),
            wifi_mac=_get_str("wifi_mac"),
            bluetooth_mac=_get_str("bluetooth_mac"),
            has_hw_home=bool(data.get("has_hw_home", True)),
            drivers=parsed_drivers,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "model_name": self.model_name,
            "serial_number": self.serial_number,
            "hardware_revision": self.hardware_revision,
            "imei": self.imei,
            "wifi_mac": self.wifi_mac,
            "bluetooth_mac": self.bluetooth_mac,
            "has_hw_home": bool(self.has_hw_home),
            "drivers": {
                str(k): str(v)
                for k, v in dict(self.drivers or {}).items()
                if str(k or "").strip() and str(v or "").strip()
            },
        }


class DeviceConfigStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.path = self.base_dir / DEVICE_CONFIG_FILE_NAME

    def load(self) -> DeviceConfig:
        if not self.path.exists():
            return DeviceConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return DeviceConfig.from_dict(data)
        except Exception:
            pass
        return DeviceConfig()

    def save(self, config: DeviceConfig) -> None:
        self.path.write_text(
            json.dumps(config.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )


@dataclass
class OSBuildConfig:
    os_name: str = "Deletescape"
    os_version: str = "0.1.0"
    build_number: int = 1
    build_id: str = ""
    channel: str = "dev"
    builder_username: str = ""
    builder_hostname: str = ""
    build_datetime: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OSBuildConfig":
        os_name = data.get("os_name", "Deletescape")
        os_version = data.get("os_version", "0.1.0")
        build_number = data.get("build_number", 1)
        build_id = data.get("build_id", "")
        channel = data.get("channel", "dev")
        builder_username = data.get("builder_username", "")
        builder_hostname = data.get("builder_hostname", "")
        build_datetime = data.get("build_datetime", "")

        return cls(
            os_name=os_name if isinstance(os_name, str) else str(os_name),
            os_version=os_version if isinstance(os_version, str) else str(os_version),
            build_number=int(build_number) if isinstance(build_number, (int, float, str)) else 1,
            build_id=build_id if isinstance(build_id, str) else str(build_id),
            channel=channel if isinstance(channel, str) else str(channel),
            builder_username=builder_username if isinstance(builder_username, str) else str(builder_username),
            builder_hostname=builder_hostname if isinstance(builder_hostname, str) else str(builder_hostname),
            build_datetime=build_datetime if isinstance(build_datetime, str) else str(build_datetime),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "build_number": self.build_number,
            "build_id": self.build_id,
            "channel": self.channel,
            "builder_username": self.builder_username,
            "builder_hostname": self.builder_hostname,
            "build_datetime": self.build_datetime,
        }


class OSBuildConfigStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.path = self.base_dir / OS_BUILD_CONFIG_FILE_NAME

    def load(self) -> OSBuildConfig:
        if not self.path.exists():
            return OSBuildConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return OSBuildConfig.from_dict(data)
        except Exception:
            pass
        return OSBuildConfig()

    def save(self, config: OSBuildConfig) -> None:
        self.path.write_text(
            json.dumps(config.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
