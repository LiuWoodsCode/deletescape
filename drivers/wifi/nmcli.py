from __future__ import annotations

import subprocess

from wifi import WifiDriverBase, WifiInfo, WifiNetwork, WifiProfile
from logger import get_logger


log = get_logger("drivers.wifi.nmcli")


def _run_nmcli(args: list[str], timeout: int = 8) -> str:
    cmd = ["nmcli", *args]
    log.debug("Running nmcli command", extra={"cmd": cmd, "timeout": int(timeout)})
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log.debug(
            "nmcli command finished",
            extra={
                "cmd": cmd,
                "returncode": int(proc.returncode),
                "stdout_len": len(str(proc.stdout or "")),
                "stderr_len": len(str(proc.stderr or "")),
            },
        )
        if proc.returncode != 0:
            log.warning("nmcli command failed", extra={"cmd": cmd, "stderr": str(proc.stderr or "")[:500]})
            return ""
        return str(proc.stdout or "")
    except Exception:
        log.exception("nmcli command raised")
        return ""


def _split_tsv_line(line: str) -> list[str]:
    cols = [part.replace("\\:", ":").strip() for part in line.strip().split(":")]
    log.debug("nmcli line split", extra={"raw": line, "columns": len(cols)})
    return cols


class NmcliWifiDriver(WifiDriverBase):
    def get_wifi_info(self) -> WifiInfo:
        log.debug("nmcli Wi-Fi get_wifi_info requested")
        status = _run_nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"])
        iface = None
        connection = None
        connected = False

        for line in status.splitlines():
            cols = _split_tsv_line(line)
            if len(cols) < 4:
                continue
            dev, typ, state, conn = cols[0], cols[1], cols[2], cols[3]
            if typ == "wifi":
                iface = dev or None
                connection = conn or None
                connected = state.lower() in {"connected", "connecting"}
                log.debug(
                    "nmcli wifi status row selected",
                    extra={"device": iface, "state": state, "connection": connection, "connected": connected},
                )
                break

        signal = None
        bssid = None
        networks = self.scan_networks()
        for net in networks:
            if connection and net.ssid == connection:
                signal = net.signal_percent
                bssid = net.bssid
                break

        info = WifiInfo(
            enabled=True if iface else None,
            connected=connected,
            interface=iface,
            ssid=connection if connected else None,
            bssid=bssid,
            signal_percent=signal,
            driver="nmcli",
        )
        log.debug(
            "nmcli Wi-Fi info parsed",
            extra={
                "interface": info.interface,
                "ssid": info.ssid,
                "connected": info.connected,
                "signal_percent": info.signal_percent,
                "bssid": info.bssid,
            },
        )
        return info

    def scan_networks(self) -> list[WifiNetwork]:
        log.debug("nmcli Wi-Fi scan requested")
        out = _run_nmcli(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,BSSID,FREQ", "dev", "wifi", "list", "--rescan", "auto"])
        nets: list[WifiNetwork] = []
        for line in out.splitlines():
            cols = _split_tsv_line(line)
            if len(cols) < 6:
                log.debug("Skipping malformed nmcli scan row", extra={"line": line})
                continue
            in_use, ssid, signal, security, bssid, freq = cols[:6]
            if not ssid:
                log.debug("Skipping hidden/empty SSID row")
                continue
            signal_i = None
            try:
                signal_i = int(signal)
            except Exception:
                pass

            freq_f = None
            try:
                freq_f = float(freq)
            except Exception:
                pass

            nets.append(
                WifiNetwork(
                    ssid=ssid,
                    signal_percent=signal_i,
                    secure=(False if security in {"", "--"} else True),
                    bssid=(bssid or None),
                    frequency_mhz=freq_f,
                    is_connected=(in_use.strip() == "*"),
                )
            )
            log.debug(
                "nmcli scan row parsed",
                extra={"ssid": ssid, "signal": signal_i, "secure": security, "bssid": bssid, "in_use": in_use},
            )
        log.debug("nmcli Wi-Fi scan parsed", extra={"count": len(nets)})
        return nets

    def list_profiles(self) -> list[WifiProfile]:
        log.debug("nmcli list_profiles requested")
        out = _run_nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"])
        profiles: list[WifiProfile] = []
        for line in out.splitlines():
            cols = _split_tsv_line(line)
            if len(cols) < 2:
                continue
            name, typ = cols[0], cols[1]
            if typ not in {"wifi", "802-11-wireless"}:
                continue
            if not name:
                continue
            profiles.append(WifiProfile(ssid=name, source="nmcli"))
            log.debug("nmcli profile parsed", extra={"ssid": name, "type": typ})
        log.debug("nmcli list_profiles parsed", extra={"count": len(profiles)})
        return profiles

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("nmcli add_profile rejected: empty ssid")
            return False

        if secure is None:
            secure = bool(password)

        out = _run_nmcli(["connection", "add", "type", "wifi", "ifname", "*", "con-name", clean_ssid, "ssid", clean_ssid])
        if not out:
            log.warning("nmcli add_profile base add failed", extra={"ssid": clean_ssid})
            return False

        if secure and password:
            sec_out = _run_nmcli(
                [
                    "connection",
                    "modify",
                    clean_ssid,
                    "wifi-sec.key-mgmt",
                    "wpa-psk",
                    "wifi-sec.psk",
                    str(password),
                ]
            )
            if not sec_out:
                log.warning("nmcli add_profile security setup failed", extra={"ssid": clean_ssid})
                return False

        log.info("nmcli add_profile result", extra={"ssid": clean_ssid, "secure": bool(secure)})
        return True

    def delete_profile(self, ssid: str) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("nmcli delete_profile rejected: empty ssid")
            return False
        out = _run_nmcli(["connection", "delete", "id", clean_ssid])
        ok = bool(out)
        log.info("nmcli delete_profile result", extra={"ssid": clean_ssid, "ok": ok})
        return ok


def create_wifi_driver() -> WifiDriverBase:
    log.info("Creating nmcli Wi-Fi driver")
    return NmcliWifiDriver()
