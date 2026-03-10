# Deletescape Driver System

This document defines how hardware drivers are implemented in Deletescape and how they translate host OS/device data into abstraction-ready data.

---

## 1) Driver Purpose

A Deletescape driver is a **host-facing adapter** for one hardware component.

It is responsible for:

- talking to host APIs/commands,
- parsing and mapping host output,
- returning component-specific data structures expected by abstraction layers.

It is **not** responsible for:

- app-facing API design,
- global fallback policy,
- cross-component orchestration.

Those belong to abstractions.

---

## 2) Driver Layout

Drivers live in:

`drivers/<component>/<driver_name>.py`

Examples:

- `drivers/batt/win32.py`
- `drivers/wifi/netsh.py`
- `drivers/location/simulated.py`
- `drivers/modem/none.py`

Every component must include:

- `none.py`
- `simulated.py`

---

## 3) Driver Selection

Runtime selection:

1. abstraction reads `deviceconfig.json` key `drivers.<component>`,
2. abstraction imports corresponding driver module,
3. abstraction validates/calls expected factory or entrypoint.

Selection helper: `driver_config.get_device_driver_name(component)`.

---

## 4) Driver Interface Patterns

Deletescape currently uses two patterns:

### 4.1 Function-return pattern (e.g., battery)

- Driver exports function, e.g. `read_battery_info()`.
- Returns model instance or dict-like payload convertible by abstraction.

### 4.2 Factory-object pattern (e.g., modem, location, wifi)

- Driver exports factory, e.g.:
  - `create_modem()`
  - `create_provider()`
  - `create_wifi_driver()`
- Returned object subclasses component base class (`ModemBase`, `LocationProviderBase`, `WifiDriverBase`).

Rule: always match the abstraction’s expected loading contract.

---

## 5) Host-to-Abstraction Conversion Rules

Drivers should convert as much host-specific representation as practical:

- parse raw text/XML/CLI output,
- convert units where directly obvious,
- map state strings to booleans/enums,
- attach source metadata when available.

Abstractions still perform final normalization to enforce canonical output.

---

## 6) Error Handling Rules

Driver code must be resilient:

- command failures should return empty/no-data results, not crash the shell,
- parser edge-cases should skip malformed rows rather than fail entire operation,
- operation APIs (`add/delete`) should return `False` on failure.

Never assume command availability (`netsh`, `nmcli`, `iwctl`, etc.).

---

## 7) Logging Requirements

Driver modules should emit detailed structured logs, including:

- command start/end (`cmd`, timeout, return code, stdout/stderr lengths),
- parsing milestones (section boundaries, extracted fields),
- fallback and rejection paths,
- final summary counts (e.g., raw vs deduped network count).

Log namespace convention:

- `drivers.<component>.<driver>`

Examples:

- `drivers.wifi.netsh`
- `drivers.batt.win32`

---

## 8) `none` Driver Contract

`none` means hardware does not exist for this device.

Expected behavior:

- return empty models (`enabled=False`, unknowns `None`, empty lists),
- mutation operations return `False`,
- do not throw for normal calls,
- log that operation is ignored/rejected.

---

## 9) `simulated` Driver Contract

`simulated` means development-mode fake hardware.

Expected behavior:

- deterministic or controlled pseudo-random output,
- realistic ranges (battery %, dBm, lat/lon drift, etc.),
- no host command dependencies,
- optional in-memory profile/state behavior for interaction testing.

---

## 10) Wi-Fi Driver Capabilities

Current `WifiDriverBase` supports:

- `get_wifi_info()`
- `scan_networks()`
- `list_profiles()`
- `add_profile(ssid, password=None, secure=None)`
- `delete_profile(ssid)`

Implementation notes:

- `netsh`: parse `wlan show interfaces/networks/profiles`; profile add/delete via `netsh wlan add/delete profile`.
- `nmcli`: use `nmcli connection show/add/modify/delete` and `nmcli dev wifi list`.
- `iwctl`: use `station show/get-networks`, `known-networks list/forget`, and connect flow for profile creation.

---

## 11) Compatibility and Stability

Driver internals can evolve as long as abstraction contracts stay stable.

If a host-specific capability is unavailable:

- return partial data gracefully,
- keep keys/types stable,
- never change abstraction method signatures from driver code.

---

## 12) Checklist for New Driver PRs

1. Driver module placed in `drivers/<component>/<name>.py`.
2. `none` and `simulated` drivers exist for the component.
3. Factory/entrypoint name matches abstraction loader.
4. Parsing handles malformed/partial host output.
5. Structured logs added for command + parse + summary phases.
6. `deviceconfig` driver key documented.
7. No app/core code calls host APIs directly.
