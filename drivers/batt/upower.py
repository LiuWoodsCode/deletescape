from __future__ import annotations

import re
import subprocess
from typing import Optional

from battery import BatteryInfo
from logger import get_logger


log = get_logger("drivers.batt.upower")


def _run_upower_dump() -> str:
    """Run `upower -d` and return raw output."""
    cmd = ["upower", "-d"]
    log.debug("Running upower dump command", extra={"cmd": cmd})
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        log.exception("upower command execution failed", extra={"cmd": cmd})
        return ""

    log.debug(
        "upower command finished",
        extra={
            "cmd": cmd,
            "returncode": result.returncode,
            "stdout_len": len(result.stdout or ""),
            "stderr_len": len(result.stderr or ""),
            "stderr": result.stderr,
        },
    )

    if result.stdout:
        log.debug("upower raw stdout", extra={"stdout": result.stdout})
    else:
        log.debug("upower raw stdout empty")

    if result.returncode != 0:
        log.warning(
            "upower command returned non-zero exit status",
            extra={
                "cmd": cmd,
                "returncode": result.returncode,
                "stderr": result.stderr,
                "stdout": result.stdout,
            },
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

        if current_header is not None and raw_line and not raw_line[:1].isspace() and raw_line.endswith(":"):
            log.debug(
                "Stopping device block at top-level non-device section",
                extra={"current_header": current_header, "section_header": raw_line},
            )
            blocks.append((current_header, current_data))
            current_header = None
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


def _describe_blocks(blocks: list[tuple[str, dict[str, str]]]) -> list[dict[str, object]]:
    return [
        {
            "device_path": device_path,
            "device_name": device_path.rsplit("/", 1)[-1],
            "keys": sorted(data.keys()),
            "field_count": len(data),
        }
        for device_path, data in blocks
    ]


def _parse_battery_block(output: str) -> dict:
    """Extract battery data, preferring `DisplayDevice` when available."""
    blocks = _iter_device_blocks(output)
    log.debug(
        "Parsed upower device blocks",
        extra={
            "device_count": len(blocks),
            "devices": _describe_blocks(blocks),
        },
    )

    display_device_data: dict[str, str] = {}
    primary_battery_data: dict[str, str] = {}

    for device_path, data in blocks:
        device_name = device_path.rsplit("/", 1)[-1].lower()
        if device_name == "displaydevice":
            display_device_data = data
            log.debug(
                "Captured DisplayDevice battery block",
                extra={"device_path": device_path, "data": data},
            )
            continue

        if not primary_battery_data and (device_name == "battery" or device_name.startswith("battery_")):
            primary_battery_data = data
            log.debug(
                "Captured primary battery block",
                extra={"device_path": device_path, "data": data},
            )

    if display_device_data:
        merged = dict(display_device_data)
        for key, value in primary_battery_data.items():
            existing = merged.get(key)
            if existing is None or existing == "" or existing.lower() in {"unknown", "n/a"}:
                merged[key] = value
                log.debug(
                    "Backfilled DisplayDevice field from primary battery block",
                    extra={"key": key, "replacement": value, "previous": existing},
                )
        log.debug(
            "Using DisplayDevice-preferred merged battery data",
            extra={
                "display_keys": sorted(display_device_data.keys()),
                "primary_keys": sorted(primary_battery_data.keys()),
                "merged_data": merged,
            },
        )
        return merged

    if primary_battery_data:
        log.debug(
            "Using primary battery data because DisplayDevice was unavailable",
            extra={"primary_data": primary_battery_data},
        )
    else:
        log.debug("No battery-like blocks found in upower output")

    return primary_battery_data


def _safe_float(value: Optional[str]) -> Optional[float]:
    if not value:
        log.debug("Float parse skipped for empty value", extra={"raw_value": value})
        return None
    try:
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)
        if not match:
            raise ValueError("no numeric token found")
        parsed = float(match.group(0))
        log.debug(
            "Parsed float from upower value",
            extra={"raw_value": value, "parsed_value": parsed, "matched_token": match.group(0)},
        )
        return parsed
    except Exception:
        log.warning("Failed to parse float from upower value", extra={"raw_value": value})
        return None


def _derive_percentage(
    percentage: Optional[float],
    *,
    energy: Optional[float],
    energy_full: Optional[float],
) -> Optional[float]:
    if percentage is not None:
        log.debug(
            "Using percentage reported directly by upower",
            extra={"reported_percentage": percentage},
        )
        return percentage

    if energy is None or energy_full is None or energy_full <= 0:
        log.debug(
            "Unable to derive percentage from energy data",
            extra={"energy": energy, "energy_full": energy_full},
        )
        return None

    derived = (energy / energy_full) * 100.0
    log.debug(
        "Derived percentage from energy and energy-full",
        extra={"energy": energy, "energy_full": energy_full, "derived_percentage": derived},
    )
    return derived


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

    log.debug("Selected battery data for normalization", extra={"data": data})

    percentage = _safe_float(data.get("percentage"))
    voltage = _safe_float(data.get("voltage"))
    energy = _safe_float(data.get("energy"))
    energy_full = _safe_float(data.get("energy-full"))
    energy_design = _safe_float(data.get("energy-full-design"))
    energy_rate = _safe_float(data.get("energy-rate"))
    percentage = _derive_percentage(percentage, energy=energy, energy_full=energy_full)

    log.debug(
        "Normalized numeric battery fields",
        extra={
            "percentage_float": percentage,
            "voltage": voltage,
            "energy": energy,
            "energy_full": energy_full,
            "energy_design": energy_design,
            "energy_rate": energy_rate,
        },
    )

    state = data.get("state", "").lower()
    is_charging = state in ("charging", "fully-charged")
    log.debug(
        "Derived charging state from upower state field",
        extra={"raw_state": data.get("state"), "normalized_state": state, "is_charging": is_charging},
    )

    # Power (W) — prefer energy-rate if present
    power = energy_rate
    log.debug("Selected battery power field", extra={"power": power, "source": "energy-rate"})

    # Health calculation (only if valid)
    health = None
    if energy_full and energy_design and energy_design > 0:
        health = (energy_full / energy_design) * 100.0
        log.debug(
            "Derived battery health from capacity data",
            extra={
                "energy_full": energy_full,
                "energy_design": energy_design,
                "health_percentage": health,
            },
        )
    else:
        log.debug(
            "Battery health unavailable from upower data",
            extra={"energy_full": energy_full, "energy_design": energy_design},
        )

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
            "raw_data": data,
            "percentage": info.percentage,
            "is_charging": info.is_charging,
            "voltage": info.voltage,
            "power": info.power,
            "health": info.health_percentage,
        },
    )

    return info
