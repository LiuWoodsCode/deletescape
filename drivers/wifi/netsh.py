from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from wifi import WifiDriverBase, WifiInfo, WifiNetwork, WifiProfile
from logger import get_logger


log = get_logger("drivers.wifi.netsh")


def _run_netsh(args: list[str], timeout: int = 8) -> str:
    cmd = ["netsh", *args]
    log.debug("Running netsh command", extra={"cmd": cmd, "timeout": int(timeout)})
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log.debug(
            "netsh command finished",
            extra={
                "cmd": cmd,
                "returncode": int(proc.returncode),
                "stdout_len": len(str(proc.stdout or "")),
                "stderr_len": len(str(proc.stderr or "")),
            },
        )
        if proc.returncode != 0:
            log.warning("netsh command failed", extra={"cmd": cmd, "stderr": str(proc.stderr or "")[:500]})
            return ""
        return str(proc.stdout or "")
    except Exception:
        log.exception("netsh command raised")
        return ""


def _find_value(text: str, key_pattern: str) -> str | None:
    m = re.search(key_pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        log.debug("Pattern not found", extra={"pattern": key_pattern})
        return None
    val = (m.group(1) or "").strip()
    log.debug("Pattern extracted", extra={"pattern": key_pattern, "value": val})
    return val or None


class NetshWifiDriver(WifiDriverBase):
    def get_wifi_info(self) -> WifiInfo:
        log.debug("Netsh Wi-Fi get_wifi_info requested")
        out = _run_netsh(["wlan", "show", "interfaces"])
        if not out:
            log.info("No netsh interface output")
            return WifiInfo(enabled=None, connected=False, driver="netsh")

        state = _find_value(out, r"^\s*State\s*:\s*(.+)$")
        interface = _find_value(out, r"^\s*Name\s*:\s*(.+)$")
        ssid = _find_value(out, r"^\s*SSID\s*:\s*(.+)$")
        bssid = _find_value(out, r"^\s*BSSID\s*:\s*(.+)$")
        signal_txt = _find_value(out, r"^\s*Signal\s*:\s*(\d+)%")
        chan_txt = _find_value(out, r"^\s*Channel\s*:\s*(\d+)$")

        signal = int(signal_txt) if signal_txt else None
        connected = bool(state and "connected" in state.lower())
        enabled = not bool(state and "disconnected" in state.lower() and not ssid)

        freq = None
        if chan_txt:
            try:
                ch = int(chan_txt)
                if 1 <= ch <= 14:
                    freq = 2407 + (ch * 5)
                else:
                    freq = 5000 + (ch * 5)
            except Exception:
                freq = None

        info = WifiInfo(
            enabled=enabled,
            connected=connected,
            interface=interface,
            ssid=ssid if connected else None,
            bssid=bssid if connected else None,
            signal_percent=signal,
            driver="netsh",
        )
        log.debug(
            "Netsh Wi-Fi info parsed",
            extra={
                "state": state,
                "interface": interface,
                "ssid": info.ssid,
                "bssid": info.bssid,
                "signal": info.signal_percent,
                "channel_frequency_mhz": freq,
                "connected": info.connected,
                "enabled": info.enabled,
            },
        )
        return info

    def scan_networks(self) -> list[WifiNetwork]:
        log.debug("Netsh Wi-Fi scan requested")
        out = _run_netsh(["wlan", "show", "networks", "mode=bssid"])
        if not out:
            log.info("No netsh scan output")
            return []

        lines = out.splitlines()
        networks: list[WifiNetwork] = []
        current_ssid: str | None = None
        current_secure: bool | None = None
        current_entry_idx: int | None = None

        for line in lines:
            stripped = line.strip()

            m_ssid = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", stripped, flags=re.IGNORECASE)
            if m_ssid:
                ssid = (m_ssid.group(1) or "").strip()
                current_ssid = ssid if ssid else None
                current_secure = None
                current_entry_idx = None
                log.debug("Scan SSID section", extra={"ssid": current_ssid})
                continue

            m_auth = re.match(r"^Authentication\s*:\s*(.*)$", stripped, flags=re.IGNORECASE)
            if m_auth:
                auth = (m_auth.group(1) or "").strip().lower()
                current_secure = "open" not in auth
                log.debug("Scan authentication parsed", extra={"ssid": current_ssid, "auth": auth, "secure": current_secure})
                continue

            m_bssid = re.match(r"^BSSID\s+\d+\s*:\s*(.*)$", stripped, flags=re.IGNORECASE)
            if m_bssid and current_ssid:
                bssid = (m_bssid.group(1) or "").strip() or None
                networks.append(
                    WifiNetwork(
                        ssid=current_ssid,
                        secure=current_secure,
                        bssid=bssid,
                    )
                )
                current_entry_idx = len(networks) - 1
                log.debug("Scan BSSID entry added", extra={"ssid": current_ssid, "bssid": bssid})
                continue

            m_signal = re.match(r"^Signal\s*:\s*(\d+)%$", stripped, flags=re.IGNORECASE)
            if m_signal and current_entry_idx is not None and 0 <= current_entry_idx < len(networks):
                try:
                    target = networks[current_entry_idx]
                    networks[current_entry_idx] = WifiNetwork(
                        ssid=target.ssid,
                        signal_percent=int(m_signal.group(1)),
                        secure=target.secure,
                        bssid=target.bssid,
                        frequency_mhz=target.frequency_mhz,
                        is_connected=target.is_connected,
                    )
                except Exception:
                    log.exception("Failed to parse signal line", extra={"line": stripped})
                continue

            m_chan = re.match(r"^Channel\s*:\s*(\d+)$", stripped, flags=re.IGNORECASE)
            if m_chan and current_entry_idx is not None and 0 <= current_entry_idx < len(networks):
                freq = None
                try:
                    ch = int(m_chan.group(1))
                    if 1 <= ch <= 14:
                        freq = float(2407 + (ch * 5))
                    else:
                        freq = float(5000 + (ch * 5))
                except Exception:
                    freq = None
                target = networks[current_entry_idx]
                networks[current_entry_idx] = WifiNetwork(
                    ssid=target.ssid,
                    signal_percent=target.signal_percent,
                    secure=target.secure,
                    bssid=target.bssid,
                    frequency_mhz=freq,
                    is_connected=target.is_connected,
                )
                log.debug("Scan channel parsed", extra={"ssid": target.ssid, "frequency_mhz": freq})

        # Netsh returns one row per BSSID. UI expects one row per SSID.
        # Keep the strongest signal per SSID while preserving representative metadata.
        dedup: dict[str, WifiNetwork] = {}
        for net in networks:
            ssid = str(net.ssid or "").strip()
            if not ssid:
                continue
            prev = dedup.get(ssid)
            if prev is None:
                dedup[ssid] = net
                continue

            prev_sig = -1 if prev.signal_percent is None else int(prev.signal_percent)
            cur_sig = -1 if net.signal_percent is None else int(net.signal_percent)
            use_current = cur_sig > prev_sig

            if use_current:
                dedup[ssid] = WifiNetwork(
                    ssid=net.ssid,
                    signal_percent=net.signal_percent,
                    secure=(net.secure if net.secure is not None else prev.secure),
                    bssid=net.bssid or prev.bssid,
                    frequency_mhz=(net.frequency_mhz if net.frequency_mhz is not None else prev.frequency_mhz),
                    is_connected=bool(net.is_connected or prev.is_connected),
                )
            else:
                dedup[ssid] = WifiNetwork(
                    ssid=prev.ssid,
                    signal_percent=prev.signal_percent,
                    secure=(prev.secure if prev.secure is not None else net.secure),
                    bssid=prev.bssid or net.bssid,
                    frequency_mhz=(prev.frequency_mhz if prev.frequency_mhz is not None else net.frequency_mhz),
                    is_connected=bool(prev.is_connected or net.is_connected),
                )

        result = list(dedup.values())
        log.debug("Netsh scan parsed", extra={"raw_count": len(networks), "dedup_count": len(result)})
        return result

    def list_profiles(self) -> list[WifiProfile]:
        log.debug("Netsh list_profiles requested")
        out = _run_netsh(["wlan", "show", "profiles"])
        if not out:
            return []

        profiles: list[WifiProfile] = []
        for line in out.splitlines():
            m = re.search(r"All User Profile\s*:\s*(.+)$", line, flags=re.IGNORECASE)
            if not m:
                continue
            ssid = str(m.group(1) or "").strip()
            if ssid:
                profiles.append(WifiProfile(ssid=ssid, source="netsh"))
                log.debug("Netsh profile parsed", extra={"ssid": ssid})
        log.debug("Netsh list_profiles parsed", extra={"count": len(profiles)})
        return profiles

    def add_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("Netsh add_profile rejected: empty ssid")
            return False

        if secure is None:
            secure = bool(password)

        auth = "WPA2PSK" if secure else "open"
        encryption = "AES" if secure else "none"
        key_xml = ""
        if secure and password:
            key_xml = (
                "<sharedKey>"
                "<keyType>passPhrase</keyType>"
                "<protected>false</protected>"
                f"<keyMaterial>{password}</keyMaterial>"
                "</sharedKey>"
            )

        xml = (
            '<?xml version="1.0"?>\n'
            '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">\n'
            f"  <name>{clean_ssid}</name>\n"
            "  <SSIDConfig><SSID><name>"
            f"{clean_ssid}"
            "</name></SSID></SSIDConfig>\n"
            "  <connectionType>ESS</connectionType>\n"
            "  <connectionMode>auto</connectionMode>\n"
            "  <MSM><security>\n"
            "    <authEncryption>"
            f"<authentication>{auth}</authentication><encryption>{encryption}</encryption><useOneX>false</useOneX>"
            "</authEncryption>"
            f"{key_xml}"
            "  </security></MSM>\n"
            "</WLANProfile>\n"
        )

        temp_path = Path(tempfile.gettempdir()) / f"deletescape_wifi_{abs(hash(clean_ssid))}.xml"
        try:
            temp_path.write_text(xml, encoding="utf-8")
            out = _run_netsh(["wlan", "add", "profile", f"filename={str(temp_path)}", "user=current"])
            ok = bool(out)
            log.info("Netsh add_profile result", extra={"ssid": clean_ssid, "ok": ok, "secure": bool(secure)})
            return ok
        except Exception:
            log.exception("Netsh add_profile failed", extra={"ssid": clean_ssid})
            return False
        finally:
            try:
                temp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except Exception:
                pass

    def delete_profile(self, ssid: str) -> bool:
        clean_ssid = str(ssid or "").strip()
        if not clean_ssid:
            log.info("Netsh delete_profile rejected: empty ssid")
            return False
        out = _run_netsh(["wlan", "delete", "profile", f"name={clean_ssid}"])
        ok = bool(out)
        log.info("Netsh delete_profile result", extra={"ssid": clean_ssid, "ok": ok})
        return ok


def create_wifi_driver() -> WifiDriverBase:
    log.info("Creating netsh Wi-Fi driver")
    return NetshWifiDriver()
