from __future__ import annotations

import re
import shutil
import subprocess

from audio import AudioDevice, AudioDriverBase, AudioInfo
from logger import get_logger


log = get_logger("drivers.audio.linux")


def _run(cmd: list[str], timeout: int = 6) -> tuple[int, str, str]:
    log.debug("Running Linux audio command", extra={"cmd": cmd, "timeout": int(timeout)})
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:
        log.exception("Linux audio command raised", extra={"cmd": cmd})
        return 1, "", ""

    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    log.debug(
        "Linux audio command finished",
        extra={
            "cmd": cmd,
            "returncode": int(proc.returncode),
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
            "stderr": stderr[:500],
        },
    )
    return int(proc.returncode), stdout, stderr


def _parse_volume_percent(output: str) -> int | None:
    percents = [int(value) for value in re.findall(r"(\d+)%", str(output or ""))]
    if percents:
        return max(0, min(100, round(sum(percents) / len(percents))))

    match = re.search(r"Volume:\s*([0-9]+(?:\.[0-9]+)?)", str(output or ""), re.IGNORECASE)
    if not match:
        return None

    try:
        return max(0, min(100, round(float(match.group(1)) * 100)))
    except Exception:
        return None


def _parse_muted(output: str) -> bool | None:
    text = str(output or "").strip().lower()
    if not text:
        return None

    if "muted" in text:
        return True

    match = re.search(r"mute:\s*(yes|no|true|false|1|0|on|off)\b", text)
    if match:
        return match.group(1) in {"yes", "true", "1", "on"}

    if text in {"yes", "true", "1", "on"}:
        return True
    if text in {"no", "false", "0", "off"}:
        return False
    if "volume:" in text:
        return False
    return None


class LinuxAudioDriver(AudioDriverBase):
    def __init__(self):
        self._has_pactl = shutil.which("pactl") is not None
        self._has_wpctl = shutil.which("wpctl") is not None
        log.info(
            "Linux audio driver initialized",
            extra={"has_pactl": bool(self._has_pactl), "has_wpctl": bool(self._has_wpctl)},
        )

    def get_audio_info(self) -> AudioInfo:
        info = self._get_pactl_info() if self._has_pactl else None
        if info is not None:
            return info

        info = self._get_wpctl_info() if self._has_wpctl else None
        if info is not None:
            return info

        return AudioInfo(driver="linux")

    def set_volume(self, percent: int) -> bool:
        value = max(0, min(100, int(percent)))
        if self._has_pactl:
            code, _, _ = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"])
            if code == 0:
                log.info("Linux audio volume set with pactl", extra={"volume_percent": value})
                return True

        if self._has_wpctl:
            code, _, _ = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value}%"])
            if code == 0:
                log.info("Linux audio volume set with wpctl", extra={"volume_percent": value})
                return True

        log.warning("Linux audio volume set failed", extra={"volume_percent": value})
        return False

    def set_muted(self, muted: bool) -> bool:
        value = "1" if muted else "0"
        if self._has_pactl:
            code, _, _ = _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", value])
            if code == 0:
                log.info("Linux audio mute set with pactl", extra={"muted": bool(muted)})
                return True

        if self._has_wpctl:
            code, _, _ = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", value])
            if code == 0:
                log.info("Linux audio mute set with wpctl", extra={"muted": bool(muted)})
                return True

        log.warning("Linux audio mute set failed", extra={"muted": bool(muted)})
        return False

    def list_output_devices(self) -> list[AudioDevice]:
        devices = self._list_pactl_output_devices() if self._has_pactl else []
        if devices:
            return devices

        return self._list_wpctl_output_devices() if self._has_wpctl else []

    def set_output_device(self, device_id: str) -> bool:
        clean_id = str(device_id or "").strip()
        if not clean_id:
            return False

        if self._has_pactl:
            code, _, _ = _run(["pactl", "set-default-sink", clean_id])
            if code == 0:
                self._move_pactl_sink_inputs(clean_id)
                log.info("Linux audio output device set with pactl", extra={"device_id": clean_id})
                return True

        if self._has_wpctl:
            code, _, _ = _run(["wpctl", "set-default", clean_id])
            if code == 0:
                log.info("Linux audio output device set with wpctl", extra={"device_id": clean_id})
                return True

        log.warning("Linux audio output device set failed", extra={"device_id": clean_id})
        return False

    def _get_pactl_info(self) -> AudioInfo | None:
        devices = self._list_pactl_output_devices()
        default = self._pactl_default_sink()

        code, volume_out, _ = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        volume = _parse_volume_percent(volume_out) if code == 0 else None

        code, mute_out, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
        muted = _parse_muted(mute_out) if code == 0 else None

        if volume is None and muted is None and not devices and not default:
            return None

        active = self._find_active_device(devices, default)
        return AudioInfo(
            volume_percent=volume,
            muted=muted,
            output_route=self._device_label(active),
            output_device_id=(active.id if active else default),
            output_device_name=self._device_label(active),
            output_devices=tuple(devices),
            driver="linux/pactl",
        )

    def _get_wpctl_info(self) -> AudioInfo | None:
        devices = self._list_wpctl_output_devices()

        code, volume_out, _ = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        volume = _parse_volume_percent(volume_out) if code == 0 else None
        muted = _parse_muted(volume_out) if code == 0 else None

        if volume is None and muted is None and not devices:
            return None

        active = self._find_active_device(devices, None)
        return AudioInfo(
            volume_percent=volume,
            muted=muted,
            output_route=self._device_label(active),
            output_device_id=(active.id if active else None),
            output_device_name=self._device_label(active),
            output_devices=tuple(devices),
            driver="linux/wpctl",
        )

    def _pactl_default_sink(self) -> str | None:
        code, out, _ = _run(["pactl", "get-default-sink"])
        if code == 0 and out.strip():
            return out.strip().splitlines()[0].strip()

        code, out, _ = _run(["pactl", "info"])
        if code != 0:
            return None
        for line in out.splitlines():
            if line.strip().lower().startswith("default sink:"):
                return line.split(":", 1)[1].strip() or None
        return None

    def _pactl_sink_descriptions(self) -> dict[str, str]:
        code, out, _ = _run(["pactl", "list", "sinks"])
        if code != 0:
            return {}

        descriptions: dict[str, str] = {}
        current_name: str | None = None
        for raw_line in out.splitlines():
            line = raw_line.strip()
            if line.startswith("Name:"):
                current_name = line.split(":", 1)[1].strip()
                continue
            if current_name and line.startswith("Description:"):
                descriptions[current_name] = line.split(":", 1)[1].strip()
        return descriptions

    def _list_pactl_output_devices(self) -> list[AudioDevice]:
        default = self._pactl_default_sink()
        descriptions = self._pactl_sink_descriptions()
        code, out, _ = _run(["pactl", "list", "short", "sinks"])
        if code != 0:
            return []

        devices: list[AudioDevice] = []
        for line in out.splitlines():
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            name = cols[1].strip()
            if not name:
                continue
            devices.append(
                AudioDevice(
                    id=name,
                    name=name,
                    description=descriptions.get(name) or name,
                    is_default=(bool(default) and name == default),
                )
            )

        return devices

    def _list_wpctl_output_devices(self) -> list[AudioDevice]:
        code, out, _ = _run(["wpctl", "status"])
        if code != 0:
            return []

        devices: list[AudioDevice] = []
        in_sinks = False
        for raw_line in out.splitlines():
            line = raw_line.strip()
            if "Sinks:" in line:
                in_sinks = True
                continue
            if not in_sinks:
                continue
            if any(marker in line for marker in ("Sources:", "Filters:", "Streams:", "Video", "Settings:")):
                break

            match = re.search(r"(\d+)\.\s+(.+?)(?:\s+\[vol:.*)?$", raw_line)
            if not match:
                continue

            device_id = match.group(1).strip()
            name = match.group(2).strip()
            prefix = raw_line[: match.start(1)]
            devices.append(
                AudioDevice(
                    id=device_id,
                    name=name,
                    description=name,
                    is_default=("*" in prefix),
                )
            )

        return devices

    def _move_pactl_sink_inputs(self, sink_name: str) -> None:
        code, out, _ = _run(["pactl", "list", "short", "sink-inputs"])
        if code != 0:
            return
        for line in out.splitlines():
            input_id = line.split(None, 1)[0].strip() if line.strip() else ""
            if not input_id:
                continue
            _run(["pactl", "move-sink-input", input_id, sink_name])

    def _find_active_device(self, devices: list[AudioDevice], default_id: str | None) -> AudioDevice | None:
        if default_id:
            for device in devices:
                if device.id == default_id:
                    return device
        for device in devices:
            if device.is_default:
                return device
        return devices[0] if devices else None

    def _device_label(self, device: AudioDevice | None) -> str | None:
        if device is None:
            return None
        return device.description or device.name or device.id


def create_audio_driver() -> AudioDriverBase:
    log.info("Creating Linux audio driver")
    return LinuxAudioDriver()
