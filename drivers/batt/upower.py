from __future__ import annotations

import subprocess
from typing import Optional

from battery import BatteryInfo
from logger import get_logger


log = get_logger("drivers.batt.upower")


def _run_upower_dump() -> str:
    """Run `upower -d` and return raw output."""
    result = subprocess.run(
        ["upower", "-d"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _parse_battery_block(output: str) -> dict:
    """Extract BAT0 block into a key/value dict."""
    lines = output.splitlines()

    in_battery = False
    data: dict[str, str] = {}

    for line in lines:
        if "Device:" in line and "battery_BAT" in line:
            in_battery = True
            continue

        if in_battery:
            if line.strip() == "":
                break  # end of block

            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()

    return data


def _safe_float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.split()[0])
    except Exception:
        return None


def read_battery_info() -> Optional[BatteryInfo]:
    log.debug("Battery upower driver read requested")

    raw = _run_upower_dump()
    if not raw:
        log.info("No output from upower")
        return None

    data = _parse_battery_block(raw)
    if not data:
        log.info("No battery block found in upower output")
        return None

    percentage = _safe_float(data.get("percentage"))
    voltage = _safe_float(data.get("voltage"))
    energy = _safe_float(data.get("energy"))
    energy_full = _safe_float(data.get("energy-full"))
    energy_design = _safe_float(data.get("energy-full-design"))
    energy_rate = _safe_float(data.get("energy-rate"))

    state = data.get("state", "").lower()
    is_charging = state in ("charging", "fully-charged")

    # Power (W) — prefer energy-rate if present
    power = energy_rate

    # Health calculation (only if valid)
    health = None
    if energy_full and energy_design and energy_design > 0:
        health = (energy_full / energy_design) * 100.0

    info = BatteryInfo(
        percentage=int(round(percentage)) if percentage is not None else None,
        is_charging=is_charging,
        voltage=voltage,
        power=power,
        design_capacity=energy_design,
        full_charge_capacity=energy_full,
        health_percentage=health,
    )

    log.debug(
        "Battery upower driver returning info",
        extra={
            "percentage": info.percentage,
            "is_charging": info.is_charging,
            "voltage": info.voltage,
            "power": info.power,
            "health": info.health_percentage,
        },
    )

    return info