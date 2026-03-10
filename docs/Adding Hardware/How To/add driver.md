# How To: Add a Driver to an Existing Abstraction

This guide covers adding a new driver when the abstraction layer already exists.

Example: add Linux battery support using `upower` under the existing `battery` abstraction.

---

## 0) Preconditions

- Existing abstraction module: `battery.py`
- Existing driver folder: `drivers/batt/`
- Existing required drivers for this component:
  - `drivers/batt/none.py`
  - `drivers/batt/simulated.py`

> Requirement reminder: every component must always have `none` and `simulated` drivers.

---

## 1) Decide Driver Name and Config Key

For this example:

- driver name: `upower`
- module path: `drivers/batt/upower.py`
- device config value: `"drivers": { "battery": "upower" }`

---

## 2) Implement the Driver Module

Create `drivers/batt/upower.py`.

The module should expose:

- `read_battery_info() -> BatteryInfo | dict | None`

Recommended implementation approach:

1. Enumerate battery device path:
   - `upower -e` and select entries like `/org/freedesktop/UPower/devices/battery_*`
2. Read details:
   - `upower -i <device_path>`
3. Parse fields:
   - `percentage` (`percentage: 74%`)
   - `state` (`charging/discharging/fully-charged`)
   - `energy-rate` (W)
   - `voltage` (V)
   - `energy-full-design` / `energy-full` (Wh) → convert to mWh for abstraction parity
4. Return `BatteryInfo(...)` with best-effort partial data.

### Minimal skeleton

```python
from __future__ import annotations

import re
import subprocess

from battery import BatteryInfo
from logger import get_logger

log = get_logger("drivers.batt.upower")


def _run(args: list[str], timeout: int = 8) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            log.warning("upower command failed", extra={"cmd": args, "rc": p.returncode})
            return ""
        return str(p.stdout or "")
    except Exception:
        log.exception("upower command raised", extra={"cmd": args})
        return ""


def read_battery_info() -> BatteryInfo:
    # 1) enumerate battery path(s)
    enum_out = _run(["upower", "-e"])
    path = None
    for line in enum_out.splitlines():
        s = line.strip()
        if "/battery_" in s:
            path = s
            break

    if not path:
        log.info("No upower battery device found")
        return BatteryInfo()

    # 2) query details
    info_out = _run(["upower", "-i", path])
    if not info_out:
        return BatteryInfo()

    # 3) parse
    pct = _parse_percent(info_out)
    charging = _parse_state(info_out)
    voltage = _parse_float_unit(info_out, r"^\s*voltage:\s*([\d.]+)\s*V", re.M)
    power = _parse_float_unit(info_out, r"^\s*energy-rate:\s*([\d.]+)\s*W", re.M)
    design_wh = _parse_float_unit(info_out, r"^\s*energy-full-design:\s*([\d.]+)\s*Wh", re.M)
    full_wh = _parse_float_unit(info_out, r"^\s*energy-full:\s*([\d.]+)\s*Wh", re.M)

    return BatteryInfo(
        percentage=pct,
        is_charging=charging,
        voltage=voltage,
        power=power,
        design_capacity=(design_wh * 1000.0 if design_wh is not None else None),
        full_charge_capacity=(full_wh * 1000.0 if full_wh is not None else None),
    )
```

Add parsing helpers (`_parse_percent`, `_parse_state`, `_parse_float_unit`) in the same file.

---

## 3) Register Driver in Abstraction Loader

Edit driver mapping in `battery.py`:

```python
module_name = {
    "winnt": "drivers.batt.win32",
    "upower": "drivers.batt.upower",
    "simulated": "drivers.batt.simulated",
    "none": "drivers.batt.none",
}.get(chosen, "drivers.batt.none")
```

Do not change public abstraction API (`get_battery_info`).

---

## 4) Select Driver in Device Config

Set in `deviceconfig.json`:

```json
{
  "drivers": {
        "battery": "upower"
  }
}
```

If omitted, fallback remains platform-specific.

---

## 5) Logging Requirements

Your driver should log:

- command invocations,
- return codes/output sizes,
- parser decisions,
- final summary fields.

Use logger namespace:

- `drivers.batt.upower`

---

## 6) Validation Checklist

1. Import path resolves (`drivers/batt/upower.py`).
2. `get_battery_info()` works with `drivers.battery=upower`.
3. Failure mode returns empty/partial `BatteryInfo` (no crash).
4. `none` and `simulated` drivers still present and working.
5. Apps like Settings battery pages continue to work unchanged.

---

## 7) Common Pitfalls

- **Unit mismatch**: `upower` capacities are commonly in Wh while Deletescape battery capacities are handled as mWh.
- **State semantics**: map `fully-charged` and `charging` carefully to boolean charging semantics.
- **Multiple batteries**: laptop + external packs may appear; either pick primary or aggregate explicitly.
- **Locale-sensitive parsing**: avoid parsing labels that can be localized; prefer robust patterns.

---

## 8) PR Scope Guidance

A driver-only PR should include:

- new driver file,
- abstraction mapping update,
- optional docs update,
- no app-level API change.

If public abstraction models or methods change, that is no longer driver-only scope.
