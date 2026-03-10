# Deletescape Hardware Abstractions

This document defines the abstraction-layer contract in Deletescape: what abstraction modules are, what data they expose, who consumes them, and what rules they must follow.

---

## 1) Architecture: OS/Driver/Abstraction Boundaries

Deletescape hardware integration is intentionally layered:

1. **Host OS / Device APIs**
   - Examples: `netsh`, `nmcli`, `iwctl`, WMI, kernel APIs, sysfs/DBus.
2. **Driver modules (`drivers/<component>/<driver>.py`)**
   - Read/translate host-specific hardware state and operations.
   - Convert host formats into component-normalized shapes.
3. **Abstraction modules (`<component>.py`)**
   - Stable API surface consumed by shell/apps.
   - Select driver from `deviceconfig.json` (`drivers.<component>`).
   - Normalize output (clamps, derived fields, defaults, failure shielding).
4. **Deletescape core + apps**
   - Consume only abstraction APIs (or shell forwarded APIs), never host APIs directly.

The abstraction layer is the compatibility boundary. Drivers can change internally without breaking apps if abstraction contracts remain stable.

---

## 2) Mandatory Driver Policy

Every hardware component in Deletescape **must** provide:

- `none` driver
  - Semantic meaning: hardware is absent/unavailable for this device.
  - Must return safe empty values; must not throw.
- `simulated` driver
  - Semantic meaning: deterministic mock/fake hardware for development/testing.
  - Should produce realistic ranges and temporal behavior.

This policy guarantees that:

- app/shell code can run on developer machines without real hardware,
- unsupported hardware degrades gracefully,
- CI/testing can use stable simulated inputs.

---

## 3) Driver Resolution Flow

Driver name resolution is centralized in `driver_config.get_device_driver_name()`.

Source of truth:

- `deviceconfig.json` → `drivers.<component>`

Fallback behavior:

- component-specific defaults (example: `battery=winnt` on Windows, `wifi=netsh` on Windows, `wifi=nmcli` on non-Windows),
- legacy key fallback (`<component>_driver`) still supported.

Abstraction modules cache loaded drivers/providers for performance and stability.

---

## 4) Current Abstractions (Contract Surface)

### 4.1 Battery (`battery.py`)

Primary model:

- `BatteryInfo`
  - `percentage`, `is_charging`
  - `voltage`, `current`, `power`
  - `design_capacity`, `full_charge_capacity`, `health_percentage`
  - `cycle_count`

Public API:

- `get_battery_info() -> BatteryInfo`

Normalization / derived behavior:

- percentage clamped to `[0, 100]`,
- power derived from `voltage * current` when absent,
- health derived from `full_charge_capacity / design_capacity` when available.

---

### 4.2 Telephony (`telephony.py`)

Primary models include:

- `SignalStrength`, `CallInfo`, `TextMessage`, `SimInfo`, `CellTowerInfo`
- `ModemBase` class contract for modem driver objects

Public APIs:

- `get_modem() -> ModemBase`
- `get_signal_strength() -> SignalStrength`

Notes:

- telephony uses object-oriented driver shape (factory returns modem instance),
- core and apps can interact with modem capabilities through `ModemBase` methods/signals.

---

### 4.3 Location (`location.py`)

Primary model:

- `LocationInfo`
  - lat/lon, altitude, accuracy, speed, heading, timestamp
  - metadata (`provider`)

Public APIs:

- `get_location_info() -> LocationInfo`
- `has_location_fix(info: LocationInfo | None = None) -> bool`
- provider override hooks (`set_location_provider`, `get_location_provider`) for tests/dev flows.

Normalization:

- latitude/longitude clamped to valid Earth bounds,
- heading wrapped into `[0, 360)`,
- speed/accuracy non-negative.

---

### 4.4 Wi-Fi (`wifi.py`)

Primary models:

- `WifiInfo` (adapter/connection state)
- `WifiNetwork` (scan result)
- `WifiProfile` (saved profile)

Public APIs:

- `get_wifi_info() -> WifiInfo`
- `scan_wifi_networks() -> list[WifiNetwork]`
- `list_wifi_profiles() -> list[WifiProfile]`
- `add_wifi_profile(ssid, *, password=None, secure=None) -> bool`
- `delete_wifi_profile(ssid) -> bool`

Normalization:

- signal percentages clamped to `[0, 100]`,
- all string fields coerced safely,
- exceptions swallowed at abstraction edge with safe fallbacks.

---

## 5) What Deletescape Core and Apps Access

### Core shell access

Core shell (`home.py`) accesses abstractions either directly or via shell API methods.

Examples (app-facing shell API methods):

- `window.get_location_info()`
- `window.get_wifi_info()`
- `window.scan_wifi_networks()`
- `window.list_wifi_profiles()`
- `window.add_wifi_profile(...)`
- `window.delete_wifi_profile(...)`

This keeps apps decoupled from driver/module internals.

### App access expectations

Apps should prefer shell-forwarded APIs (`self.window.*`) where available, then optionally fallback to abstraction module imports if needed for standalone behavior.

Apps should **never** call host OS commands directly (`netsh`, `nmcli`, etc.).

---

## 6) Abstraction Authoring Rules

When creating or evolving an abstraction module:

1. **Define immutable normalized dataclasses** as the public contract.
2. **Provide one stable convenience entrypoint** (`get_<component>_info` or equivalent).
3. **Hide host variance in drivers**, not in apps/core.
4. **Normalize aggressively**:
   - ranges,
   - units,
   - nullability,
   - metadata defaults.
5. **Never propagate raw driver exceptions** to callers.
6. **Cache driver/provider instances** when appropriate.
7. **Document driver names and config key** (`drivers.<component>`).
8. **Require and document `none` and `simulated` drivers**.

---

## 7) Failure Semantics

Abstraction APIs are best-effort and should be fail-safe:

- on driver import failure → fallback to `none` behavior or safe empty model,
- on parse failure → return partial/empty normalized model,
- on operational failure (e.g., add/delete profile) → return `False`, not exception.

This preserves shell stability under unsupported/partially-supported host platforms.

---

## 8) Logging and Observability

Driver modules should emit detailed structured logs for:

- command invocation + return status,
- parser milestones,
- fallback transitions,
- normalized output summaries.

Abstractions should keep logs lower-volume and focused on selection/fallback events.

---

## 9) Data Conversion Responsibility Matrix

- **Driver responsibility**
  - convert host-native fields/units into draft component values,
  - handle command/API-specific quirks,
  - emit detailed trace/debug logs.

- **Abstraction responsibility**
  - select driver,
  - canonicalize types/ranges,
  - fill derived fields,
  - guarantee stable return contract.

- **Core/App responsibility**
  - consume abstraction contracts,
  - never parse host-native payloads.

---

## 10) Device Configuration Example

```json
{
  "manufacturer": "Example",
  "model": "ExampleDevice",
  "drivers": {
    "battery": "winnt",
    "modem": "simulated",
    "location": "simulated",
    "wifi": "netsh"
  }
}
```

For any new component, add `drivers.<component>` and maintain both `none` + `simulated` implementations.
