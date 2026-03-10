# How To: Add a New Hardware Abstraction

This guide explains how to add a brand-new abstraction end-to-end.

Example: add a **Playdate crank** abstraction.

Goal: apps can read crank state through stable APIs, independent of host implementation.

---

## 0) Design Rules

Before writing code:

1. Define a normalized data model (abstraction contract).
2. Keep host-specific logic in drivers only.
3. Require two baseline drivers:
   - `none` (feature absent)
   - `simulated` (test/demo fallback)
4. Expose abstraction through shell APIs if apps need access.

---

## 1) Define the Abstraction Contract

Create `crank.py` in project root.

Suggested model:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class CrankInfo:
    supported: bool = False
    attached: bool = False
    angle_deg: Optional[float] = None
    delta_deg: Optional[float] = None
    rpm: Optional[float] = None
    docked: Optional[bool] = None
```

Suggested API surface:

- `get_crank_info() -> CrankInfo`
- `is_crank_supported() -> bool`

Contract behavior:

- never raise to callers,
- return safe defaults on errors,
- normalize values (angles, rpm, booleans).

---

## 2) Add Driver Package Structure

Create folder:

- `drivers/crank/`

Create files:

- `drivers/crank/__init__.py`
- `drivers/crank/none.py`
- `drivers/crank/simulated.py`

Optional real drivers (platform-specific) can be added later:

- `drivers/crank/playdate_bridge.py`
- `drivers/crank/hid.py`

---

## 3) Implement Mandatory Baseline Drivers

### `drivers/crank/none.py`

Return unsupported state deterministically.

```python
from crank import CrankInfo


def read_crank_info() -> CrankInfo:
    return CrankInfo(supported=False, attached=False, angle_deg=None, delta_deg=None, rpm=None, docked=None)
```

### `drivers/crank/simulated.py`

Return synthetic values for UI/testing.

```python
import math
import time

from crank import CrankInfo


def read_crank_info() -> CrankInfo:
    t = time.time()
    angle = (t * 120.0) % 360.0
    rpm = 60.0 + 30.0 * math.sin(t)
    return CrankInfo(
        supported=True,
        attached=True,
        angle_deg=angle,
        delta_deg=2.0,
        rpm=max(0.0, rpm),
        docked=False,
    )
```

---

## 4) Add Driver Selection and Loading in `crank.py`

Pattern should match existing abstractions (`battery.py`, `location.py`, `wifi.py`).

Driver name resolution:

- use `get_device_driver_name("crank")`
- map name to module path
- fallback to `none`

Example mapping:

```python
module_name = {
    "playdate_bridge": "drivers.crank.playdate_bridge",
    "hid": "drivers.crank.hid",
    "simulated": "drivers.crank.simulated",
    "none": "drivers.crank.none",
}.get(chosen, "drivers.crank.none")
```

Then call `read_crank_info()` from loaded module and normalize return value.

---

## 5) Add Config Support

### `config.py`

Add default mapping entry in `DeviceConfig.default_drivers`:

```python
"crank": "none"
```

### `driver_config.py`

Add OS-aware default if needed; otherwise default to `none`.

Then device config can select driver:

```json
{
  "drivers": {
        "crank": "simulated"
  }
}
```

---

## 6) Expose Through Shell API (if apps need it)

In shell host (currently `home.py`), add methods such as:

- `get_crank_info()`
- `is_crank_supported()`

These should delegate to abstraction only, not directly to drivers.

---

## 7) Add an App-Level Test Surface

Create minimal test app (similar to `apps/location_test`) that displays:

- `supported`
- `attached`
- `angle_deg`
- `delta_deg`
- `rpm`
- `docked`

Refresh periodically and confirm no crashes across drivers.

---

## 8) Logging and Error Policy

Use logger namespaces:

- abstraction: `crank`
- drivers: `drivers.crank.<name>`

Rules:

- abstraction logs selection/fallback/normalization,
- driver logs host I/O and parse decisions,
- errors are logged, then converted to safe abstraction output.

---

## 9) Normalization Rules (Recommended)

- Clamp angle into `[0, 360)` if non-null.
- Clamp rpm to `>= 0`.
- `supported=False` implies all non-boolean telemetry may be `None`.
- Preserve `docked` as `None` when host cannot determine dock state.

This keeps UI/app behavior consistent across heterogeneous drivers.

---

## 10) Completion Checklist

- [ ] `crank.py` exists with stable API and safe failure semantics.
- [ ] `drivers/crank/none.py` implemented.
- [ ] `drivers/crank/simulated.py` implemented.
- [ ] Driver selection wired through `driver_config.py`/`config.py`.
- [ ] Shell API exposure added (if app-facing).
- [ ] Example/test app verifies runtime behavior.
- [ ] Logs are sufficiently detailed for diagnostics.

---

## 11) Scope Boundaries

A clean initial abstraction PR should avoid:

- changing unrelated abstractions,
- host-specific assumptions in app code,
- introducing hard dependency on real hardware.

Start with `none` + `simulated`, then add real hardware drivers in follow-up PRs.
