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


def _iter_device_blocks(output: str) -> list[tuple[str, dict[str, str]]]:
    blocks: list[tuple[str, dict[str, str]]] = []
    current_header: str | None = None
    current_data: dict[str, str] = {}

    for raw_line in output.splitlines():
        if raw_line.startswith("Device:"):
            if current_header is not None:
                blocks.append((current_header, current_data))
            current_header = raw_line.split(":", 1)[1].strip()
            current_data = {}
            continue

        if current_header is None:
            continue

        line = raw_line.strip()
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        current_data[key.strip()] = value.strip()

    if current_header is not None:
        blocks.append((current_header, current_data))

    return blocks


def _parse_battery_block(output: str) -> dict:
    """Extract battery data, preferring `DisplayDevice` when available."""
    display_device_data: dict[str, str] = {}
    primary_battery_data: dict[str, str] = {}

    for device_path, data in _iter_device_blocks(output):
        device_name = device_path.rsplit("/", 1)[-1].lower()
        if device_name == "displaydevice":
            display_device_data = data
            continue

        if not primary_battery_data and (device_name == "battery" or device_name.startswith("battery_")):
            primary_battery_data = data

    if display_device_data:
        merged = dict(display_device_data)
        for key, value in primary_battery_data.items():
            existing = merged.get(key)
            if existing is None or existing == "" or existing.lower() in {"unknown", "n/a"}:
                merged[key] = value
        return merged

    return primary_battery_data


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
