from __future__ import annotations

from dataclasses import dataclass
import importlib
import threading
from typing import Optional

from driver_config import get_device_driver_name

from logger import PROCESS_START, get_logger
log = get_logger("hal.battery")

@dataclass(frozen=True)
class BatteryInfo:
    """Normalized battery information.

    Notes on units:
    - percentage: 0..100
    - voltage: volts
    - current: amps (sign depends on provider; many systems report discharge as negative)
    - power: watts (derived from voltage * current when not provided)
    - design_capacity/full_charge_capacity: milliwatt-hours when sourced from Windows WMI
    """

    percentage: Optional[int] = None
    is_charging: Optional[bool] = None

    voltage: Optional[float] = None
    current: Optional[float] = None
    power: Optional[float] = None

    design_capacity: Optional[float] = None
    full_charge_capacity: Optional[float] = None
    health_percentage: Optional[float] = None

    cycle_count: Optional[int] = None


# Cache powercfg results because generating/parsing the report is expensive.
_POWERCFG_REPORT_LOCK = threading.Lock()
_POWERCFG_REPORT_RAN = False
_POWERCFG_REPORT_CACHED: Optional[BatteryInfo] = None

_BATTERY_DRIVER_LOCK = threading.Lock()
_BATTERY_DRIVER_NAME: str | None = None
_BATTERY_DRIVER_READER = None


def get_battery_info() -> BatteryInfo:
    """Return battery info from the configured battery driver.

    Driver comes from `deviceconfig.json` at `drivers.battery`.
    Supported names:
    - `winnt` -> `drivers.batt.win32`
    - `simulated` -> `drivers.batt.simulated`
    - `none` -> `drivers.batt.none`
    """

    info = BatteryInfo()
    try:
        reader = _get_battery_driver_reader()
        if callable(reader):
            raw = reader()
            if isinstance(raw, BatteryInfo):
                info = raw
            elif isinstance(raw, dict):
                info = BatteryInfo(
                    percentage=(int(raw.get("percentage")) if raw.get("percentage") is not None else None),
                    is_charging=(bool(raw.get("is_charging")) if raw.get("is_charging") is not None else None),
                    voltage=(float(raw.get("voltage")) if raw.get("voltage") is not None else None),
                    current=(float(raw.get("current")) if raw.get("current") is not None else None),
                    power=(float(raw.get("power")) if raw.get("power") is not None else None),
                    design_capacity=(
                        float(raw.get("design_capacity"))
                        if raw.get("design_capacity") is not None
                        else None
                    ),
                    full_charge_capacity=(
                        float(raw.get("full_charge_capacity"))
                        if raw.get("full_charge_capacity") is not None
                        else None
                    ),
                    health_percentage=(
                        float(raw.get("health_percentage"))
                        if raw.get("health_percentage") is not None
                        else None
                    ),
                    cycle_count=(int(raw.get("cycle_count")) if raw.get("cycle_count") is not None else None),
                )
    except Exception:
        info = BatteryInfo()

    return _with_derived_fields(info)


def _get_battery_driver_reader():
    global _BATTERY_DRIVER_NAME, _BATTERY_DRIVER_READER

    chosen = str(get_device_driver_name("battery", fallback="winnt")).strip().lower() or "winnt"
    module_name = {
        "winnt": "drivers.batt.win32",
        "upower": "drivers.batt.upower",
        "simulated": "drivers.batt.simulated",
        "none": "drivers.batt.none",
    }.get(chosen, "drivers.batt.none")

    with _BATTERY_DRIVER_LOCK:
        if _BATTERY_DRIVER_READER is not None and _BATTERY_DRIVER_NAME == module_name:
            return _BATTERY_DRIVER_READER

        try:
            module = importlib.import_module(module_name)
            reader = getattr(module, "read_battery_info", None)
            _BATTERY_DRIVER_READER = reader if callable(reader) else None
            _BATTERY_DRIVER_NAME = module_name
        except Exception:
            _BATTERY_DRIVER_READER = None
            _BATTERY_DRIVER_NAME = module_name

        return _BATTERY_DRIVER_READER


def _try_windows_powercfg_battery_report_cached() -> Optional[BatteryInfo]:
    """Run the powercfg provider at most once per process."""

    global _POWERCFG_REPORT_RAN, _POWERCFG_REPORT_CACHED

    if _POWERCFG_REPORT_RAN:
        return _POWERCFG_REPORT_CACHED

    with _POWERCFG_REPORT_LOCK:
        if _POWERCFG_REPORT_RAN:
            return _POWERCFG_REPORT_CACHED

        _POWERCFG_REPORT_CACHED = _try_windows_powercfg_battery_report()
        _POWERCFG_REPORT_RAN = True
        return _POWERCFG_REPORT_CACHED


def _merge_missing_battery_info(primary: BatteryInfo, extra: BatteryInfo) -> BatteryInfo:
    """Merge two BatteryInfo objects, only filling fields missing in primary."""

    return BatteryInfo(
        percentage=primary.percentage if primary.percentage is not None else extra.percentage,
        is_charging=primary.is_charging if primary.is_charging is not None else extra.is_charging,
        voltage=primary.voltage if primary.voltage is not None else extra.voltage,
        current=primary.current if primary.current is not None else extra.current,
        power=primary.power if primary.power is not None else extra.power,
        design_capacity=(
            primary.design_capacity if primary.design_capacity is not None else extra.design_capacity
        ),
        full_charge_capacity=(
            primary.full_charge_capacity
            if primary.full_charge_capacity is not None
            else extra.full_charge_capacity
        ),
        health_percentage=(
            primary.health_percentage
            if primary.health_percentage is not None
            else extra.health_percentage
        ),
        cycle_count=primary.cycle_count if primary.cycle_count is not None else extra.cycle_count,
    )


def _with_derived_fields(info: BatteryInfo) -> BatteryInfo:
    power = info.power
    if power is None and info.voltage is not None and info.current is not None:
        power = info.voltage * info.current

    health_percentage = info.health_percentage
    if (
        health_percentage is None
        and info.design_capacity
        and info.full_charge_capacity
        and info.design_capacity > 0
    ):
        health_percentage = (info.full_charge_capacity / info.design_capacity) * 100.0

    percentage = info.percentage
    if percentage is not None:
        percentage = max(0, min(100, int(round(float(percentage)))))

    return BatteryInfo(
        percentage=percentage,
        is_charging=info.is_charging,
        voltage=info.voltage,
        current=info.current,
        power=power,
        design_capacity=info.design_capacity,
        full_charge_capacity=info.full_charge_capacity,
        health_percentage=health_percentage,
        cycle_count=info.cycle_count,
    )


def _try_psutil() -> Optional[BatteryInfo]:
    try:
        import psutil  # type: ignore

        battery = psutil.sensors_battery()
        if battery is None or battery.percent is None:
            return None

        return BatteryInfo(
            percentage=int(round(float(battery.percent))),
            is_charging=bool(getattr(battery, "power_plugged", False)),
        )
    except Exception:
        return None


def _try_windows_api() -> Optional[BatteryInfo]:
    # Avoid importing ctypes on non-Windows unnecessarily.
    try:
        import os

        if os.name != "nt":
            return None

        import ctypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_ubyte),
                ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]

        status = SYSTEM_POWER_STATUS()
        ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
        if not ok:
            return None

        percent = None if status.BatteryLifePercent == 255 else int(status.BatteryLifePercent)
        is_charging = None
        if status.ACLineStatus in (0, 1):
            is_charging = bool(status.ACLineStatus == 1)

        return BatteryInfo(percentage=percent, is_charging=is_charging)
    except Exception:
        return None


def _try_windows_powercfg_battery_report() -> Optional[BatteryInfo]:
    """Best-effort battery enrichment via `powercfg /batteryreport /XML`.

    This can provide:
    - design_capacity (mWh)
    - full_charge_capacity (mWh)
    - cycle_count

    If multiple batteries are present, capacities are summed and cycle_count is the max.
    Percentage/charging are taken from the WinAPI provider.
    """

    try:
        import os

        if os.name != "nt":
            return None

        import subprocess
        import tempfile
        import xml.etree.ElementTree as ET
        from pathlib import Path

        out_path = Path(tempfile.gettempdir()) / "deletescape_batteryreport.xml"

        # Generate the XML report. powercfg writes directly to the output file.
        proc = subprocess.run(
            [
                "powercfg",
                "/batteryreport",
                "/output",
                str(out_path),
                "/XML",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return None
        if not out_path.exists():
            return None

        try:
            tree = ET.parse(str(out_path))
            root = tree.getroot()

            # Default namespace in the report.
            ns = {"br": "http://schemas.microsoft.com/battery/2012"}
            batteries = root.findall(".//br:Batteries/br:Battery", ns)
            if not batteries:
                return None

            def _get_int_text(elem: ET.Element, tag: str) -> Optional[int]:
                child = elem.find(f"br:{tag}", ns)
                if child is None or child.text is None:
                    return None
                txt = child.text.strip()
                if not txt:
                    return None
                try:
                    return int(txt)
                except Exception:
                    return None

            total_design: Optional[float] = 0.0
            total_full: Optional[float] = 0.0
            any_design = False
            any_full = False
            max_cycles: Optional[int] = None

            for b in batteries:
                d = _get_int_text(b, "DesignCapacity")
                f = _get_int_text(b, "FullChargeCapacity")
                c = _get_int_text(b, "CycleCount")

                if d is not None:
                    any_design = True
                    total_design = (total_design or 0.0) + float(d)
                if f is not None:
                    any_full = True
                    total_full = (total_full or 0.0) + float(f)
                if c is not None:
                    max_cycles = c if max_cycles is None else max(max_cycles, c)

            design_capacity = float(total_design) if any_design else None
            full_charge_capacity = float(total_full) if any_full else None

            base = _try_windows_api() or BatteryInfo()
            return BatteryInfo(
                percentage=base.percentage,
                is_charging=base.is_charging,
                design_capacity=design_capacity,
                full_charge_capacity=full_charge_capacity,
                cycle_count=max_cycles,
            )
        finally:
            try:
                out_path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except Exception:
                pass

    except Exception:
        return None


def _try_windows_wmi() -> Optional[BatteryInfo]:
    """Best-effort enrichment via Windows WMI (requires `wmi` module).

    Uses `root\\wmi` classes when available:
    - BatteryStaticData (DesignedCapacity)
    - BatteryFullChargedCapacity (FullChargedCapacity)
    - BatteryCycleCount (CycleCount)
    - BatteryStatus (Voltage, Current)

    Any missing fields remain None.
    """

    try:
        import os

        if os.name != "nt":
            return None

        import wmi  # type: ignore

        w = wmi.WMI(namespace="root\\wmi")

        designed_capacity = None
        full_charged_capacity = None
        cycle_count = None
        voltage_v = None
        current_a = None

        try:
            static = w.BatteryStaticData()
            if static:
                obj = static[0]
                val = getattr(obj, "DesignedCapacity", None)
                if val is not None:
                    designed_capacity = float(val)
        except Exception:
            pass

        try:
            full = w.BatteryFullChargedCapacity()
            if full:
                obj = full[0]
                val = getattr(obj, "FullChargedCapacity", None)
                if val is not None:
                    full_charged_capacity = float(val)
        except Exception:
            pass

        try:
            cyc = w.BatteryCycleCount()
            if cyc:
                obj = cyc[0]
                val = getattr(obj, "CycleCount", None)
                if val is not None:
                    cycle_count = int(val)
        except Exception:
            pass

        try:
            stat = w.BatteryStatus()
            if stat:
                obj = stat[0]
                mv = getattr(obj, "Voltage", None)
                ma = getattr(obj, "Current", None)
                if mv is not None:
                    voltage_v = float(mv) / 1000.0
                if ma is not None:
                    current_a = float(ma) / 1000.0
        except Exception:
            pass

        # Get percentage/charging via the Windows API fallback so the top-line UI is always present.
        base = _try_windows_api() or BatteryInfo()

        return BatteryInfo(
            percentage=base.percentage,
            is_charging=base.is_charging,
            voltage=voltage_v,
            current=current_a,
            design_capacity=designed_capacity,
            full_charge_capacity=full_charged_capacity,
            cycle_count=cycle_count,
        )
    except Exception:
        return None
