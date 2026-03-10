from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from battery import BatteryInfo
from logger import get_logger


log = get_logger("drivers.batt.win32")


_POWERCFG_REPORT_LOCK = threading.Lock()
_POWERCFG_REPORT_RAN = False
_POWERCFG_REPORT_CACHED: BatteryInfo | None = None


def read_battery_info() -> BatteryInfo:
    log.debug("Battery win32 driver read requested", extra={"os_name": os.name})
    info = _try_windows_wmi()
    if info is None:
        log.debug("WMI provider unavailable, trying psutil")
        info = _try_psutil()
    if info is None:
        log.debug("psutil provider unavailable, trying WinAPI")
        info = _try_windows_api()
    if info is None:
        log.info("All primary providers unavailable, returning empty BatteryInfo")
        info = BatteryInfo()

    if os.name == "nt":
        extra = _try_windows_powercfg_battery_report_cached()
        if extra is not None:
            log.debug("Merging powercfg battery enrichment")
            info = _merge_missing_battery_info(info, extra)
        else:
            log.debug("No powercfg enrichment available")

    log.debug(
        "Battery win32 driver returning",
        extra={
            "percentage": info.percentage,
            "is_charging": info.is_charging,
            "voltage": info.voltage,
            "current": info.current,
            "design_capacity": info.design_capacity,
            "full_charge_capacity": info.full_charge_capacity,
            "cycle_count": info.cycle_count,
        },
    )
    return info


def _try_windows_powercfg_battery_report_cached() -> BatteryInfo | None:
    global _POWERCFG_REPORT_RAN, _POWERCFG_REPORT_CACHED

    if _POWERCFG_REPORT_RAN:
        log.debug("Using cached powercfg battery report")
        return _POWERCFG_REPORT_CACHED

    with _POWERCFG_REPORT_LOCK:
        if _POWERCFG_REPORT_RAN:
            log.debug("Using cached powercfg battery report (post-lock)")
            return _POWERCFG_REPORT_CACHED
        log.debug("Generating powercfg battery report cache")
        _POWERCFG_REPORT_CACHED = _try_windows_powercfg_battery_report()
        _POWERCFG_REPORT_RAN = True
        return _POWERCFG_REPORT_CACHED


def _merge_missing_battery_info(primary: BatteryInfo, extra: BatteryInfo) -> BatteryInfo:
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
            primary.full_charge_capacity if primary.full_charge_capacity is not None else extra.full_charge_capacity
        ),
        health_percentage=(
            primary.health_percentage if primary.health_percentage is not None else extra.health_percentage
        ),
        cycle_count=primary.cycle_count if primary.cycle_count is not None else extra.cycle_count,
    )


def _try_psutil() -> BatteryInfo | None:
    try:
        log.debug("Trying psutil battery provider")
        import psutil  # type: ignore

        battery = psutil.sensors_battery()
        if battery is None or battery.percent is None:
            log.info("psutil provider returned no battery data")
            return None

        info = BatteryInfo(
            percentage=int(round(float(battery.percent))),
            is_charging=bool(getattr(battery, "power_plugged", False)),
        )
        log.debug("psutil provider success", extra={"percentage": info.percentage, "is_charging": info.is_charging})
        return info
    except Exception:
        log.exception("psutil provider failed")
        return None


def _try_windows_api() -> BatteryInfo | None:
    try:
        if os.name != "nt":
            log.debug("Skipping WinAPI provider on non-nt OS")
            return None
        log.debug("Trying WinAPI battery provider")

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
            log.warning("GetSystemPowerStatus returned failure")
            return None

        percent = None if status.BatteryLifePercent == 255 else int(status.BatteryLifePercent)
        is_charging = None
        if status.ACLineStatus in (0, 1):
            is_charging = bool(status.ACLineStatus == 1)

        info = BatteryInfo(percentage=percent, is_charging=is_charging)
        log.debug(
            "WinAPI provider success",
            extra={"percentage": info.percentage, "is_charging": info.is_charging, "ac_line": int(status.ACLineStatus)},
        )
        return info
    except Exception:
        log.exception("WinAPI provider failed")
        return None


def _try_windows_powercfg_battery_report() -> BatteryInfo | None:
    try:
        if os.name != "nt":
            log.debug("Skipping powercfg provider on non-nt OS")
            return None

        out_path = Path(tempfile.gettempdir()) / "deletescape_batteryreport.xml"

        proc = subprocess.run(
            ["powercfg", "/batteryreport", "/output", str(out_path), "/XML"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        log.debug(
            "powercfg command finished",
            extra={
                "returncode": int(proc.returncode),
                "stdout_len": len(str(proc.stdout or "")),
                "stderr_len": len(str(proc.stderr or "")),
                "output_path": str(out_path),
            },
        )
        if proc.returncode != 0:
            log.warning("powercfg command failed", extra={"stderr": str(proc.stderr or "")[:500]})
            return None
        if not out_path.exists():
            log.warning("powercfg output path missing", extra={"output_path": str(out_path)})
            return None

        try:
            tree = ET.parse(str(out_path))
            root = tree.getroot()

            ns = {"br": "http://schemas.microsoft.com/battery/2012"}
            batteries = root.findall(".//br:Batteries/br:Battery", ns)
            if not batteries:
                log.info("powercfg report parsed but no batteries found")
                return None

            def _get_int_text(elem: ET.Element, tag: str) -> int | None:
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

            total_design = 0.0
            total_full = 0.0
            any_design = False
            any_full = False
            max_cycles: int | None = None

            for battery in batteries:
                design = _get_int_text(battery, "DesignCapacity")
                full = _get_int_text(battery, "FullChargeCapacity")
                cycles = _get_int_text(battery, "CycleCount")

                if design is not None:
                    any_design = True
                    total_design += float(design)
                if full is not None:
                    any_full = True
                    total_full += float(full)
                if cycles is not None:
                    max_cycles = cycles if max_cycles is None else max(max_cycles, cycles)

                log.debug(
                    "powercfg battery row parsed",
                    extra={"design": design, "full": full, "cycles": cycles},
                )

            design_capacity = float(total_design) if any_design else None
            full_charge_capacity = float(total_full) if any_full else None

            base = _try_windows_api() or BatteryInfo()
            info = BatteryInfo(
                percentage=base.percentage,
                is_charging=base.is_charging,
                design_capacity=design_capacity,
                full_charge_capacity=full_charge_capacity,
                cycle_count=max_cycles,
            )
            log.debug(
                "powercfg enrichment parsed",
                extra={
                    "design_capacity": design_capacity,
                    "full_charge_capacity": full_charge_capacity,
                    "cycle_count": max_cycles,
                },
            )
            return info
        finally:
            try:
                out_path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except Exception:
                log.exception("Failed to cleanup powercfg temp report", extra={"output_path": str(out_path)})
                pass
    except Exception:
        log.exception("powercfg provider failed")
        return None


def _try_windows_wmi() -> BatteryInfo | None:
    try:
        if os.name != "nt":
            log.debug("Skipping WMI provider on non-nt OS")
            return None
        log.debug("Trying WMI battery provider")

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
                val = getattr(static[0], "DesignedCapacity", None)
                if val is not None:
                    designed_capacity = float(val)
        except Exception:
            log.exception("WMI BatteryStaticData query failed")
            pass

        try:
            full = w.BatteryFullChargedCapacity()
            if full:
                val = getattr(full[0], "FullChargedCapacity", None)
                if val is not None:
                    full_charged_capacity = float(val)
        except Exception:
            log.exception("WMI BatteryFullChargedCapacity query failed")
            pass

        try:
            cyc = w.BatteryCycleCount()
            if cyc:
                val = getattr(cyc[0], "CycleCount", None)
                if val is not None:
                    cycle_count = int(val)
        except Exception:
            log.exception("WMI BatteryCycleCount query failed")
            pass

        try:
            stat = w.BatteryStatus()
            if stat:
                mv = getattr(stat[0], "Voltage", None)
                ma = getattr(stat[0], "Current", None)
                if mv is not None:
                    voltage_v = float(mv) / 1000.0
                if ma is not None:
                    current_a = float(ma) / 1000.0
        except Exception:
            log.exception("WMI BatteryStatus query failed")
            pass

        base = _try_windows_api() or BatteryInfo()
        info = BatteryInfo(
            percentage=base.percentage,
            is_charging=base.is_charging,
            voltage=voltage_v,
            current=current_a,
            design_capacity=designed_capacity,
            full_charge_capacity=full_charged_capacity,
            cycle_count=cycle_count,
        )
        log.debug(
            "WMI provider success",
            extra={
                "percentage": info.percentage,
                "is_charging": info.is_charging,
                "voltage": info.voltage,
                "current": info.current,
                "design_capacity": info.design_capacity,
                "full_charge_capacity": info.full_charge_capacity,
                "cycle_count": info.cycle_count,
            },
        )
        return info
    except Exception:
        log.exception("WMI provider failed")
        return None
