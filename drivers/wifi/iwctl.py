from __future__ import annotations

import re
import subprocess

from wifi import WifiDriverBase, WifiInfo, WifiNetwork, WifiProfile
from logger import get_logger


log = get_logger("drivers.wifi.iwctl")


def _run_iwctl(args: list[str], timeout: int = 8) -> str:
    cmd = ["iwctl", *args]
    log.debug("Running iwctl command", extra={"cmd": cmd, "timeout": int(timeout)})
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log.debug(
            "iwctl command finished",
            extra={
                "cmd": cmd,
                "returncode": int(proc.returncode),
                "stdout_len": len(str(proc.stdout or "")),
                "stderr_len": len(str(proc.stderr or "")),
            },
        )
        if proc.returncode != 0:
            log.warning("iwctl command failed", extra={"cmd": cmd, "stderr": str(proc.stderr or "")[:500]})
            return ""
        return str(proc.stdout or "")
    except Exception:
        log.exception("iwctl command raised")
        return ""


class IwctlWifiDriver(WifiDriverBase):
    def _get_station(self) -> str | None:
        log.debug("iwctl station discovery requested")
        out = _run_iwctl(["station", "list"])
        for line in out.splitlines():
            text = line.strip()
            if not text or text.lower().startswith("station"):
                continue
            parts = text.split()
            if parts:
                log.debug("iwctl station parsed", extra={"station": parts[0]})
                return parts[0]
        log.info("iwctl station list returned no station")
        return None

    def get_wifi_info(self) -> WifiInfo:
        log.debug("iwctl get_wifi_info requested")
        station = self._get_station()
        if not station:
            return WifiInfo(enabled=None, connected=False, driver="iwctl")

        show = _run_iwctl(["station", station, "show"])
        state_match = re.search(r"State\s+([A-Za-z]+)", show)
        connected = bool(state_match and state_match.group(1).lower() == "connected")

        ssid_match = re.search(r"Connected network\s+(.+)", show)
        ssid = ssid_match.group(1).strip() if ssid_match else None

        signal = None
        signal_match = re.search(r"RSSI\s+(-?\d+)", show)
        if signal_match:
            try:
                rssi = int(signal_match.group(1))
                signal = max(0, min(100, int((rssi + 100) * 2)))
            except Exception:
                signal = None

        info = WifiInfo(
            enabled=True,
            connected=connected,
            interface=station,
            ssid=ssid if connected else None,
            signal_percent=signal,
            driver="iwctl",
        )
        log.debug(
            "iwctl Wi-Fi info parsed",
            extra={"station": station, "ssid": info.ssid, "connected": info.connected, "signal": info.signal_percent},
        )
        return info

    def scan_networks(self) -> list[WifiNetwork]:
        log.debug("iwctl scan_networks requested")
        station = self._get_station()
        if not station:
            return []

        out = _run_iwctl(["station", station, "get-networks"])
        nets: list[WifiNetwork] = []
        for raw in out.splitlines():
            line = raw.strip()
            if not line or "SSID" in line or line.startswith("-"):
                continue
            clean = line.replace(">", " ").replace("*", " ").strip()
            parts = [p for p in clean.split("  ") if p.strip()]
            if not parts:
                log.debug("Skipping unparsable iwctl row", extra={"line": line})
                continue

            ssid = parts[0].strip()
            if not ssid:
                continue

            secure = True
            low = clean.lower()
            if "open" in low:
                secure = False

            signal = None
            bars_match = re.search(r"(\*{1,4})", line)
            if bars_match:
                bars = len(bars_match.group(1))
                signal = int(round((bars / 4.0) * 100))

            nets.append(
                WifiNetwork(
                    ssid=ssid,
                    signal_percent=signal,
                    secure=secure,
                    is_connected=("connected" in low),
                )
            )
            log.debug(
                "iwctl scan row parsed",
                extra={"ssid": ssid, "signal": signal, "secure": secure, "connected": ("connected" in low)},
            )
        log.debug("iwctl scan parsed", extra={"count": len(nets)})
        return nets

    def list_profiles(self) -> list[WifiProfile]:
        log.debug("iwctl list_profiles requested")
        out = _run_iwctl(["known-networks", "list"])
        profiles: list[WifiProfile] = []
        for raw in out.splitlines():
            line = raw.strip()
            if not line or line.lower().startswith("name") or line.startswith("-"):
                continue
            parts = [p for p in line.split("  ") if p.strip()]
            if not parts:
                continue
            ssid = parts[0].strip()
            if not ssid:
                continue
            secure = None
            low = line.lower()
            if "open" in low:
                secure = False
            elif "psk" in low or "8021x" in low:
                secure = True
            profiles.append(WifiProfile(ssid=ssid, secure=secure, source="iwctl"))
            log.debug("iwctl profile parsed", extra={"ssid": ssid, "secure": secure})
        log.debug("iwctl list_profiles parsed", extra={"count": len(profiles)})
        return profiles

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("iwctl add_profile rejected: empty ssid")
            return False

        station = self._get_station()
        if not station:
            log.warning("iwctl add_profile failed: no station")
            return False

        args = ["station", station]
        if password:
            args.extend(["--passphrase", str(password)])
        args.extend(["connect", clean_ssid])
        out = _run_iwctl(args, timeout=20)
        ok = bool(out)
        log.info(
            "iwctl add_profile result",
            extra={"ssid": clean_ssid, "ok": ok, "has_password": bool(password), "secure": secure},
        )
        return ok

    def delete_profile(self, ssid: str) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("iwctl delete_profile rejected: empty ssid")
            return False
        out = _run_iwctl(["known-networks", clean_ssid, "forget"])
        ok = bool(out)
        log.info("iwctl delete_profile result", extra={"ssid": clean_ssid, "ok": ok})
        return ok


def create_wifi_driver() -> WifiDriverBase:
    log.info("Creating iwctl Wi-Fi driver")
    return IwctlWifiDriver()
