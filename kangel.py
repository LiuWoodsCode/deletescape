import ctypes
import ctypes.util
import datetime as _dt
import getpass
import inspect
import json
import os
import pdb
import platform
import shutil
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
import time
import zipfile
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import getpass
import hashlib
from pathlib import Path

if os.name != "nt":
    try:
        import fcntl
        import select
        import struct
        import termios
    except Exception:  # pragma: no cover - optional on some platforms
        fcntl = None
        select = None
        struct = None
        termios = None
else:  # pragma: no cover - Windows fallback path
    fcntl = None
    select = None
    struct = None
    termios = None

try:
    import paramiko
except Exception:  # pragma: no cover - optional dependency at runtime
    paramiko = None

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency at runtime
    psutil = None

import audio as audio_hal
import battery as battery_hal
import display as display_hal
import location as location_hal
import media as media_hal
import sensors as sensors_hal
import telephony as telephony_hal
import thermals as thermals_hal
import vibration as vibration_hal
import wifi as wifi_hal
from app_registry import discover_apps
from config import CONFIG_FILE_NAME, DeviceConfigStore, OSBuildConfigStore
from fs_layout import get_user_data_layout

KANGEL_PORT = 2222
KANGEL_HOST_KEY_NAME = "kangel_host_key.pem"
KANGEL_HISTORY_FILE_NAME = "history.json"
KANGEL_HISTORY_LIMIT = 500
KANGEL_WELCOME_LINES = (
    "Welcome, P-chan. Keep the stream stable.",
)
KANGEL_PROMPT = "KAngel> "
KANGEL_COMMANDS = (
    "help",
    "info",
    "recovery",
    "apps",
    "launch",
    "install",
    "uninstall",
    "running",
    "bgapps",
    "kill",
    "logs",
    "logstream",
    "media",
    "button",
    "screenshot",
    "status",
    "control",
    "crash",
    "exec",
    "shell",
    "py",
    "pdb",
    "history",
    "clear",
    "exit",
    "quit",
    "logout",
)


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _json_safe(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 8:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return _json_safe(asdict(value), _depth=_depth + 1)
        except Exception:
            return repr(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = _json_safe(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, _depth=_depth + 1) for item in value]
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _json_dumps(value: Any) -> str:
    return json.dumps(_json_safe(value), indent=2, sort_keys=True)


def _parse_enabled_token(value: str) -> bool | None:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "y", "on", "enable", "enabled", "mute", "muted"}:
        return True
    if lowered in {"0", "false", "no", "n", "off", "disable", "disabled", "unmute", "unmuted"}:
        return False
    return None


def default_kangel_enabled_for_channel(channel: str) -> bool:
    return str(channel or "").strip().lower() == "dev"


def load_kangel_enabled(base_dir: Path) -> bool:
    try:
        build = OSBuildConfigStore(base_dir=base_dir).load()
        default_enabled = default_kangel_enabled_for_channel(getattr(build, "channel", ""))
    except Exception:
        default_enabled = False

    cfg_path = Path(base_dir) / CONFIG_FILE_NAME
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "kangel_enabled" in data:
            return _boolish(data.get("kangel_enabled"))
    except Exception:
        pass
    return default_enabled


def _probe_primary_ip() -> str:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0] or "")
    except Exception:
        return ""
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _collect_ip_addresses() -> list[str]:
    values: list[str] = []
    if psutil is not None:
        try:
            for addrs in psutil.net_if_addrs().values():
                for addr in addrs:
                    if getattr(addr, "family", None) == socket.AF_INET:
                        ip = str(getattr(addr, "address", "") or "").strip()
                        if ip and ip != "127.0.0.1":
                            values.append(ip)
        except Exception:
            pass
    if not values:
        primary = _probe_primary_ip()
        if primary:
            values.append(primary)
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _decode_ssh_text(value: Any) -> str:
    try:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value or "")
    except Exception:
        return ""


def _sanitize_pty_size(width: Any, height: Any) -> tuple[int, int]:
    try:
        cols = int(width)
    except Exception:
        cols = 80
    try:
        rows = int(height)
    except Exception:
        rows = 24
    return max(20, cols), max(5, rows)


def _set_pty_window_size(fd: int, cols: int, rows: int) -> None:
    if fcntl is None or struct is None or termios is None or not hasattr(termios, "TIOCSWINSZ"):
        return
    cols, rows = _sanitize_pty_size(cols, rows)
    packed = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)


def _default_shell_argv() -> list[str]:
    if os.name == "nt":
        for candidate in (
            ["pwsh", "-NoLogo", "-NoProfile"],
            ["powershell.exe", "-NoLogo", "-NoProfile"],
            [os.environ.get("COMSPEC", "cmd.exe")],
        ):
            program = str(candidate[0] or "").strip()
            if not program:
                continue
            if program.lower().endswith(".exe") or os.path.sep in program:
                return candidate
            if shutil_which(program):
                return candidate
        return ["cmd.exe"]
    return [os.environ.get("SHELL") or "/bin/sh", "-i"]


def shutil_which(program: str) -> str | None:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    extensions = [""]
    if os.name == "nt":
        extensions = os.environ.get("PATHEXT", ".EXE").split(os.pathsep)
    for directory in paths:
        directory = str(directory or "").strip()
        if not directory:
            continue
        for extension in extensions:
            candidate = Path(directory) / f"{program}{extension}"
            if candidate.exists():
                return str(candidate)
    return None


def _generate_pin_from_key(path: Path) -> str:
    try:
        data = path.read_bytes()
    except Exception:
        return None

    # hash the file contents
    digest = hashlib.sha256(data).hexdigest()

    # turn into a 6-digit PIN (stable, numeric)
    pin_int = int(digest, 16) % 1_000_000
    return f"{pin_int:06d}"


def authenticate_system_user(username: str, password: str) -> tuple[bool, str]:
    if not username:
        return False, "username is required"
    if password is None:
        return False, "password is required"

    current_user = getpass.getuser()

    key_path = Path("userdata/Data/System/KAngel/kangel_host_key.pem")
    expected_pin = _generate_pin_from_key(key_path)

    if expected_pin is None:
        return False, "unable to read host key"

    if username == current_user and password == expected_pin:
        return True, "ok"
    else:
        return False, "username or password incorrect"
    
class _KAngelSSHServer(paramiko.ServerInterface if paramiko is not None else object):
    def __init__(self) -> None:
        super().__init__()
        self.event = threading.Event()
        self.exec_command: str | None = None
        self.username = ""
        self.auth_error = ""
        self.pty_term = "xterm-256color"
        self.pty_cols = 80
        self.pty_rows = 24
        self.env_requests: dict[str, str] = {}
        self.pty_resize_handler = None

    def check_channel_request(self, kind: str, chanid: int) -> int:
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username: str, password: str) -> int:
        ok, message = authenticate_system_user(username, password)
        if ok:
            self.username = str(username or "")
            return paramiko.AUTH_SUCCESSFUL
        self.auth_error = message
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes) -> bool:
        self.pty_term = _decode_ssh_text(term) or "xterm-256color"
        self.pty_cols, self.pty_rows = _sanitize_pty_size(width, height)
        return True

    def check_channel_env_request(self, channel, name, value) -> bool:
        key = _decode_ssh_text(name).strip()
        if not key:
            return False
        self.env_requests[key] = _decode_ssh_text(value)
        return True

    def check_channel_window_change_request(self, channel, width, height, pixelwidth, pixelheight) -> bool:
        self.pty_cols, self.pty_rows = _sanitize_pty_size(width, height)
        handler = self.pty_resize_handler
        if callable(handler):
            try:
                handler(self.pty_cols, self.pty_rows)
            except Exception:
                pass
        return True

    def check_channel_shell_request(self, channel) -> bool:
        self.event.set()
        return True

    def check_channel_exec_request(self, channel, command) -> bool:
        try:
            if isinstance(command, bytes):
                self.exec_command = command.decode("utf-8", errors="replace")
            else:
                self.exec_command = str(command or "")
        except Exception:
            self.exec_command = ""
        self.event.set()
        return True


class KAngelSession:
    def __init__(
        self,
        manager: "KAngelManager",
        channel,
        username: str,
        *,
        pty_term: str = "xterm-256color",
        pty_cols: int = 80,
        pty_rows: int = 24,
        env_requests: dict[str, str] | None = None,
    ) -> None:
        self.manager = manager
        self.channel = channel
        self.username = str(username or "")
        self._python_locals: dict[str, Any] = {}
        self._pty_term = str(pty_term or "xterm-256color")
        self._pty_cols, self._pty_rows = _sanitize_pty_size(pty_cols, pty_rows)
        self._env_requests = dict(env_requests or {})
        self._active_pty_master_fd: int | None = None
        self._pty_lock = threading.Lock()
        self._history: list[str] = self.manager.load_history()

    def write(self, text: str) -> None:
        if not text:
            return
        try:
            self.channel.sendall(text.replace("\n", "\r\n"))
        except Exception:
            pass

    def writeln(self, text: str = "") -> None:
        self.write(text + "\n")

    def update_pty_size(self, cols: int, rows: int) -> None:
        self._pty_cols, self._pty_rows = _sanitize_pty_size(cols, rows)
        master_fd = self._active_pty_master_fd
        if master_fd is None:
            return
        with self._pty_lock:
            if self._active_pty_master_fd != master_fd:
                return
            try:
                _set_pty_window_size(master_fd, self._pty_cols, self._pty_rows)
            except Exception:
                pass

    def _clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def _redraw_input(self, prompt: str, text: str, cursor: int) -> None:
        cursor = max(0, min(cursor, len(text)))
        self.write("\r\x1b[2K")
        self.write(f"{prompt}{text}")
        tail = len(text) - cursor
        if tail > 0:
            self.write(f"\x1b[{tail}D")

    def _read_escape_sequence(self) -> bytes:
        seq = bytearray(b"\x1b")
        previous_timeout = self._set_channel_timeout(0.02)
        try:
            for _ in range(8):
                try:
                    chunk = self.channel.recv(1)
                except socket.timeout:
                    break
                except Exception:
                    break
                if not chunk:
                    break
                seq.extend(chunk)
                if chunk in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                    break
        finally:
            self._restore_channel_timeout(previous_timeout)
        return bytes(seq)

    def _escape_shell_completion(self, value: str) -> str:
        out: list[str] = []
        for char in str(value or ""):
            if char in " \t\\\"'`()[]{}$&;|<>":
                out.append("\\")
            out.append(char)
        return "".join(out)

    def _dedupe_completions(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            item = str(value or "")
            if not item or item in seen:
                continue
            seen.add(item)
            out.append(item)
        return sorted(out, key=lambda item: item.lower())

    def _common_completion_prefix(self, candidates: list[str]) -> str:
        if not candidates:
            return ""
        prefix = candidates[0]
        for item in candidates[1:]:
            limit = min(len(prefix), len(item))
            idx = 0
            while idx < limit and prefix[idx] == item[idx]:
                idx += 1
            prefix = prefix[:idx]
            if not prefix:
                break
        return prefix

    def _apply_completion_candidates(
        self,
        fragment: str,
        candidates: list[str],
        *,
        append_space: bool = True,
    ) -> tuple[str | None, list[str]]:
        options = self._dedupe_completions(candidates)
        if not options:
            return None, []
        if len(options) == 1:
            value = options[0]
            if append_space and not value.endswith(("/", "\\")):
                value += " "
            return value, options
        prefix = self._common_completion_prefix(options)
        if prefix and prefix != fragment:
            return prefix, options
        return None, options

    def _find_token_start(self, text: str) -> int:
        idx = len(text)
        while idx > 0 and not text[idx - 1].isspace():
            idx -= 1
        return idx

    def _resolve_completion_path(self, fragment: str) -> tuple[Path, str, str]:
        raw_fragment = str(fragment or "")
        sep = os.path.sep
        altsep = os.path.altsep or ""
        if raw_fragment.endswith((sep, altsep)) if altsep else raw_fragment.endswith(sep):
            display_dir = raw_fragment
            name_prefix = ""
        else:
            display_dir, name_prefix = os.path.split(raw_fragment)
        expanded_dir = os.path.expanduser(display_dir or ".")
        path = Path(expanded_dir)
        if not path.is_absolute():
            path = self.manager.base_dir / path
        return path, display_dir, name_prefix

    def _path_completion_candidates(self, fragment: str) -> list[str]:
        directory, display_dir, name_prefix = self._resolve_completion_path(fragment)
        if not directory.exists() or not directory.is_dir():
            return []
        candidates: list[str] = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if name_prefix and not child.name.startswith(name_prefix):
                continue
            if display_dir:
                if display_dir.endswith((os.path.sep, os.path.altsep or os.path.sep)):
                    rendered = f"{display_dir}{child.name}"
                else:
                    rendered = f"{display_dir}{os.path.sep}{child.name}"
            else:
                rendered = child.name
            if child.is_dir():
                rendered += os.path.sep
            candidates.append(self._escape_shell_completion(rendered))
        return candidates

    def _executable_completion_candidates(self, fragment: str) -> list[str]:
        prefix = str(fragment or "")
        pathext = [ext.lower() for ext in os.environ.get("PATHEXT", ".EXE").split(os.pathsep)] if os.name == "nt" else []
        candidates: list[str] = []
        seen: set[str] = set()
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            directory = str(directory or "").strip()
            if not directory:
                continue
            path = Path(directory)
            if not path.exists() or not path.is_dir():
                continue
            try:
                entries = list(path.iterdir())
            except Exception:
                continue
            for entry in entries:
                name = entry.name
                if prefix:
                    if os.name == "nt":
                        if not name.lower().startswith(prefix.lower()):
                            continue
                    elif not name.startswith(prefix):
                        continue
                if not entry.is_file():
                    continue
                if os.name == "nt":
                    if pathext and entry.suffix.lower() not in pathext:
                        continue
                elif not os.access(entry, os.X_OK):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                candidates.append(self._escape_shell_completion(name))
        return candidates

    def _shell_completion_candidates(self, fragment: str, *, first_token: bool) -> list[str]:
        raw_fragment = str(fragment or "")
        wants_path = (
            raw_fragment.startswith(("~", ".", os.path.sep))
            or (os.path.altsep and raw_fragment.startswith(os.path.altsep))
            or os.path.sep in raw_fragment
            or (os.path.altsep and os.path.altsep in raw_fragment)
        )
        candidates: list[str] = []
        if first_token and not wants_path:
            candidates.extend(self._executable_completion_candidates(raw_fragment))
        candidates.extend(self._path_completion_candidates(raw_fragment))
        return self._dedupe_completions(candidates)

    def _command_completion_candidates(self, fragment: str) -> list[str]:
        return [command for command in KANGEL_COMMANDS if command.startswith(fragment)]

    def _app_completion_candidates(self, fragment: str) -> list[str]:
        ok, payload = self._host_call(
            lambda host: sorted((getattr(host, "apps", {}) or {}).keys())
        )
        if not ok or not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, str) and item.startswith(fragment)]

    def _status_completion_candidates(self, fragment: str) -> list[str]:
        topics = ["all", "battery", "telephony", "audio", "display", "sensors", "location", "thermal", "wifi", "vibration", "media"]
        return [item for item in topics if item.startswith(fragment)]

    def _media_completion_candidates(self, fragment: str) -> list[str]:
        commands = [
            "active",
            "callbacks",
            "clear",
            "command",
            "fake",
            "inspect",
            "list",
            "sessions",
        ]
        commands.extend(sorted(getattr(media_hal, "MEDIA_COMMANDS", set())))
        return [item for item in self._dedupe_completions(commands) if item.startswith(fragment)]

    def _button_completion_candidates(self, fragment: str) -> list[str]:
        return [item for item in ["home", "power"] if item.startswith(fragment)]

    def _log_completion_candidates(self, fragment: str) -> list[str]:
        logs_dir = self.manager.base_dir / "logs"
        candidates = ["latest"]
        try:
            for item in logs_dir.iterdir():
                if item.is_file():
                    candidates.append(item.name)
        except Exception:
            pass
        return [item for item in self._dedupe_completions(candidates) if item.startswith(fragment)]

    def _complete_plain_line(self, line: str, cursor: int) -> tuple[str | None, int, list[str]]:
        before = line[:cursor]
        after = line[cursor:]
        token_start = self._find_token_start(before)
        fragment = before[token_start:]
        replacement, candidates = self._apply_completion_candidates(
            fragment,
            self._command_completion_candidates(fragment),
        )
        if replacement is None:
            return None, cursor, candidates
        updated = before[:token_start] + replacement + after
        return updated, len(before[:token_start] + replacement), candidates

    def _complete_shell_like_text(self, text: str, cursor: int) -> tuple[str | None, int, list[str]]:
        before = text[:cursor]
        after = text[cursor:]
        token_start = self._find_token_start(before)
        prefix = before[:token_start]
        fragment = before[token_start:]
        replacement, candidates = self._apply_completion_candidates(
            fragment,
            self._shell_completion_candidates(fragment, first_token=not prefix.strip()),
        )
        if replacement is None:
            return None, cursor, candidates
        updated = prefix + replacement + after
        return updated, len(prefix + replacement), candidates

    def _complete_kangel_input(self, line: str, cursor: int) -> tuple[str | None, int, list[str]]:
        before = line[:cursor]
        stripped = before.lstrip()
        indent = before[: len(before) - len(stripped)]

        if stripped.startswith("!"):
            updated, new_cursor, candidates = self._complete_shell_like_text(stripped[1:], len(stripped) - 1)
            if updated is None:
                return None, cursor, candidates
            final = indent + "!" + updated + line[cursor:]
            return final, len(indent) + 1 + new_cursor, candidates

        parts = stripped.split(None, 1)
        first = parts[0] if parts else ""

        if not parts or (len(parts) == 1 and not stripped.endswith(" ")):
            return self._complete_plain_line(line, cursor)

        if first in {"exec", "shell"}:
            command_offset = len(indent) + len(first) + 1
            shell_text = line[command_offset:]
            shell_cursor = max(0, cursor - command_offset)
            updated, new_cursor, candidates = self._complete_shell_like_text(shell_text, shell_cursor)
            if updated is None:
                return None, cursor, candidates
            final = line[:command_offset] + updated
            return final, command_offset + new_cursor, candidates

        before_token = line[: self._find_token_start(before)]
        fragment = before[self._find_token_start(before):]
        if first == "launch":
            replacement, candidates = self._apply_completion_candidates(fragment, self._app_completion_candidates(fragment))
        elif first in {"uninstall", "kill"}:
            replacement, candidates = self._apply_completion_candidates(fragment, self._app_completion_candidates(fragment))
        elif first in {"logs", "logstream"}:
            replacement, candidates = self._apply_completion_candidates(fragment, self._log_completion_candidates(fragment))
        elif first == "status":
            replacement, candidates = self._apply_completion_candidates(fragment, self._status_completion_candidates(fragment))
        elif first == "media":
            replacement, candidates = self._apply_completion_candidates(fragment, self._media_completion_candidates(fragment))
        elif first == "button":
            replacement, candidates = self._apply_completion_candidates(fragment, self._button_completion_candidates(fragment))
        else:
            return None, cursor, []
        if replacement is None:
            return None, cursor, candidates
        updated = before_token + replacement + line[cursor:]
        return updated, len(before_token + replacement), candidates

    def _show_completion_candidates(self, prompt: str, text: str, cursor: int, candidates: list[str]) -> None:
        if not candidates:
            self.write("\a")
            return
        self.write("\n")
        limit = 40
        for item in candidates[:limit]:
            self.writeln(item)
        if len(candidates) > limit:
            self.writeln(f"... and {len(candidates) - limit} more")
        self._redraw_input(prompt, text, cursor)

    def _append_history_entry(self, command: str) -> None:
        value = str(command or "").strip()
        if not value:
            return
        if self._history and self._history[-1] == value:
            return
        self._history.append(value)
        self._history = self._history[-KANGEL_HISTORY_LIMIT:]
        self.manager.append_history_entry(value)

    def _readline(self, prompt: str = "") -> str | None:
        text = ""
        cursor = 0
        history_index: int | None = None
        history_saved_current = ""
        self._redraw_input(prompt, text, cursor)
        while True:
            try:
                chunk = self.channel.recv(1)
            except Exception:
                return None
            if not chunk:
                return None
            if chunk in (b"\r", b"\n"):
                self.write("\n")
                return text
            if chunk in (b"\x08", b"\x7f"):
                if cursor > 0:
                    text = text[: cursor - 1] + text[cursor:]
                    cursor -= 1
                    self._redraw_input(prompt, text, cursor)
                else:
                    self.write("\a")
                continue
            if chunk == b"\x03":
                self.write("^C\n")
                return ""
            if chunk == b"\x04":
                if not text:
                    self.write("^D\n")
                    return None
                if cursor < len(text):
                    text = text[:cursor] + text[cursor + 1 :]
                    self._redraw_input(prompt, text, cursor)
                else:
                    self.write("\a")
                continue
            if chunk == b"\t":
                updated, new_cursor, candidates = self._complete_kangel_input(text, cursor)
                if updated is not None:
                    text = updated
                    cursor = new_cursor
                    self._redraw_input(prompt, text, cursor)
                else:
                    self._show_completion_candidates(prompt, text, cursor, candidates)
                continue
            if chunk == b"\x01":
                cursor = 0
                self._redraw_input(prompt, text, cursor)
                continue
            if chunk == b"\x05":
                cursor = len(text)
                self._redraw_input(prompt, text, cursor)
                continue
            if chunk == b"\x0b":
                text = text[:cursor]
                self._redraw_input(prompt, text, cursor)
                continue
            if chunk == b"\x15":
                text = text[cursor:]
                cursor = 0
                self._redraw_input(prompt, text, cursor)
                continue
            if chunk == b"\x0c":
                self._clear_screen()
                self._redraw_input(prompt, text, cursor)
                continue
            if chunk == b"\x1b":
                seq = self._read_escape_sequence()
                if seq in {b"\x1b[A", b"\x1bOA"}:
                    if self._history:
                        if history_index is None:
                            history_saved_current = text
                            history_index = len(self._history) - 1
                        else:
                            history_index = max(0, history_index - 1)
                        text = self._history[history_index]
                        cursor = len(text)
                        self._redraw_input(prompt, text, cursor)
                    else:
                        self.write("\a")
                    continue
                if seq in {b"\x1b[B", b"\x1bOB"}:
                    if history_index is None:
                        self.write("\a")
                    else:
                        history_index += 1
                        if history_index >= len(self._history):
                            history_index = None
                            text = history_saved_current
                        else:
                            text = self._history[history_index]
                        cursor = len(text)
                        self._redraw_input(prompt, text, cursor)
                    continue
                if seq in {b"\x1b[C", b"\x1bOC"}:
                    if cursor < len(text):
                        cursor += 1
                        self._redraw_input(prompt, text, cursor)
                    else:
                        self.write("\a")
                    continue
                if seq in {b"\x1b[D", b"\x1bOD"}:
                    if cursor > 0:
                        cursor -= 1
                        self._redraw_input(prompt, text, cursor)
                    else:
                        self.write("\a")
                    continue
                if seq in {b"\x1b[H", b"\x1bOH", b"\x1b[1~", b"\x1b[7~"}:
                    cursor = 0
                    self._redraw_input(prompt, text, cursor)
                    continue
                if seq in {b"\x1b[F", b"\x1bOF", b"\x1b[4~", b"\x1b[8~"}:
                    cursor = len(text)
                    self._redraw_input(prompt, text, cursor)
                    continue
                if seq == b"\x1b[3~":
                    if cursor < len(text):
                        text = text[:cursor] + text[cursor + 1 :]
                        self._redraw_input(prompt, text, cursor)
                    else:
                        self.write("\a")
                    continue
                continue
            try:
                decoded = chunk.decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            if not decoded or not decoded.isprintable():
                continue
            if history_index is not None:
                history_index = None
                history_saved_current = ""
            text = text[:cursor] + decoded + text[cursor:]
            cursor += len(decoded)
            self._redraw_input(prompt, text, cursor)

    def _host_call(self, fn, timeout: float = 5.0) -> tuple[bool, Any]:
        host = self.manager.host_window
        if host is None:
            return False, "shell UI is unavailable"
        done = threading.Event()
        result: dict[str, Any] = {}

        def _invoke() -> None:
            try:
                result["value"] = fn(host)
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        try:
            runner = getattr(host, "run_on_ui_thread", None)
            if callable(runner):
                runner(_invoke)
            else:
                _invoke()
        except Exception as exc:
            return False, str(exc)

        if not done.wait(timeout):
            return False, "timed out waiting for UI thread"
        if "error" in result:
            return False, str(result["error"])
        return True, result.get("value")

    def _system_call(self, fn, timeout: float = 5.0) -> tuple[bool, Any]:
        if self.manager.host_window is not None:
            return self._host_call(lambda _host: fn(), timeout=timeout)
        try:
            return True, fn()
        except Exception as exc:
            return False, str(exc)

    def _host_method_or_fallback(self, method_name: str, fallback, *args, timeout: float = 5.0, **kwargs) -> tuple[bool, Any]:
        host = self.manager.host_window
        if host is not None:
            def _call(host_obj):
                fn = getattr(host_obj, method_name, None)
                if callable(fn):
                    return fn(*args, **kwargs)
                return fallback(*args, **kwargs)

            return self._host_call(_call, timeout=timeout)
        try:
            return True, fallback(*args, **kwargs)
        except Exception as exc:
            return False, str(exc)

    def _refresh_host_app_registry(self) -> None:
        self._host_call(
            lambda host: (
                setattr(host, "apps", host.load_apps())
                if callable(getattr(host, "load_apps", None))
                else None
            )
        )

    def _validate_pkg_archive(self, archive: zipfile.ZipFile) -> None:
        members = archive.infolist()
        if not members:
            raise ValueError("Package is empty")
        for member in members:
            normalized = member.filename.replace("\\", "/")
            if normalized.startswith("/") or ".." in Path(normalized).parts:
                raise ValueError("Package contains unsafe paths")

    def _locate_pkg_app_root(self, extracted_root: Path) -> Path:
        manifest_here = extracted_root / "manifest.json"
        main_here = extracted_root / "main.py"
        if manifest_here.exists() and main_here.exists():
            return extracted_root

        child_dirs = [p for p in extracted_root.iterdir() if p.is_dir()]
        if len(child_dirs) == 1:
            child = child_dirs[0]
            if (child / "manifest.json").exists() and (child / "main.py").exists():
                return child

        raise ValueError("Could not locate app root in package")

    def _read_pkg_manifest_info(self, app_root: Path, *, package_path: Path | None = None) -> dict[str, Any]:
        manifest_path = app_root / "manifest.json"
        main_path = app_root / "main.py"
        assets_dir = app_root / "Assets"

        if not manifest_path.exists():
            raise ValueError("Package is missing manifest.json")
        if not main_path.exists():
            raise ValueError("Package is missing main.py")
        if not assets_dir.exists() or not assets_dir.is_dir():
            raise ValueError("Package is missing Assets directory")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest.json must contain an object")

        app_id_raw = manifest.get("appId") or manifest.get("app_id") or manifest.get("id")
        app_id = str(app_id_raw).strip() if app_id_raw is not None else ""
        if not app_id:
            raise ValueError("Manifest missing appId")

        display_name_raw = manifest.get("displayName") or manifest.get("display_name") or app_id
        display_name = str(display_name_raw).strip() if display_name_raw is not None else app_id

        layout = get_user_data_layout(self.manager.base_dir)
        return {
            "package": str(package_path) if package_path is not None else "",
            "app_id": app_id,
            "display_name": display_name or app_id,
            "version": str(manifest.get("version")) if manifest.get("version") is not None else "unknown",
            "build": str(manifest.get("build")) if manifest.get("build") is not None else "unknown",
            "replace": bool((layout.applications / app_id).exists()),
        }

    def _install_pkg_file(self, package_path: Path) -> dict[str, Any]:
        if package_path.suffix.lower() != ".pkg":
            raise ValueError("Only .pkg files are supported")
        if not package_path.exists() or not package_path.is_file():
            raise ValueError(f"Package not found: {package_path}")

        layout = get_user_data_layout(self.manager.base_dir)
        layout.ensure_directories()

        with zipfile.ZipFile(package_path, "r") as archive:
            self._validate_pkg_archive(archive)
            with tempfile.TemporaryDirectory(prefix="deletescape_kangel_pkginstall_") as tmp_dir:
                extract_root = Path(tmp_dir)
                archive.extractall(extract_root)
                app_root = self._locate_pkg_app_root(extract_root)
                info = self._read_pkg_manifest_info(app_root, package_path=package_path)
                app_id = str(info["app_id"])

                builtin_destination = self.manager.base_dir / "apps" / app_id
                if builtin_destination.exists():
                    raise ValueError(f"Package app ID conflicts with built-in app: {app_id}")

                destination = layout.applications / app_id
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(app_root, destination)
                info["installed_to"] = str(destination)
                return info

    def _resolve_user_app_descriptor(self, app_id: str):
        app_id = str(app_id or "").strip()
        if not app_id:
            return None
        layout = get_user_data_layout(self.manager.base_dir)
        layout.ensure_directories()
        try:
            return discover_apps(layout.applications).get(app_id)
        except Exception:
            return None

    def _uninstall_user_app(self, app_id: str, *, keep_data: bool = False, host=None) -> dict[str, Any]:
        app_id = str(app_id or "").strip()
        if not app_id:
            raise ValueError("app id is required")

        layout = get_user_data_layout(self.manager.base_dir)
        layout.ensure_directories()
        descriptor = self._resolve_user_app_descriptor(app_id)
        app_dir = descriptor.folder if descriptor is not None else (layout.applications / app_id)
        display_name = getattr(descriptor, "display_name", None) or app_id

        if not app_dir.exists():
            raise ValueError(f"User application is not installed: {app_id}")

        try:
            user_apps_root = layout.applications.resolve()
            resolved_app_dir = app_dir.resolve()
            if not resolved_app_dir.is_relative_to(user_apps_root):
                raise ValueError("Refusing to uninstall an app outside userdata/Applications")
        except AttributeError:
            user_apps_root = layout.applications.resolve()
            resolved_app_dir = app_dir.resolve()
            if user_apps_root not in resolved_app_dir.parents and resolved_app_dir != user_apps_root:
                raise ValueError("Refusing to uninstall an app outside userdata/Applications")

        if host is not None:
            try:
                running_apps = getattr(host, "_running_apps", {}) or {}
                terminate = getattr(host, "_terminate_app", None)
                if callable(terminate) and app_id in running_apps:
                    terminate(app_id)
            except Exception:
                pass

        removed_data = False
        shutil.rmtree(app_dir)

        data_dir = layout.app_data_dir(app_id)
        if not keep_data and data_dir.exists():
            shutil.rmtree(data_dir)
            removed_data = True

        if host is not None:
            try:
                loader = getattr(host, "load_apps", None)
                if callable(loader):
                    host.apps = loader()
            except Exception:
                pass

        return {
            "app_id": app_id,
            "display_name": display_name,
            "removed_app": str(app_dir),
            "removed_data": removed_data,
            "kept_data": bool(keep_data),
        }

    def _running_app_snapshot(self) -> tuple[bool, Any]:
        def _snapshot(host):
            running_apps = getattr(host, "_running_apps", {}) or {}
            active_app_id = getattr(host, "active_app_id", None)
            apps = getattr(host, "apps", {}) or {}

            task_counts: dict[str, int] = {}
            bg_manager = getattr(host, "background_tasks", None)
            for entry in list((getattr(bg_manager, "_tasks", {}) or {}).values()):
                try:
                    handle = getattr(entry, "handle", None)
                    task_app_id = str(getattr(handle, "app_id", "") or "")
                    if task_app_id:
                        task_counts[task_app_id] = task_counts.get(task_app_id, 0) + 1
                except Exception:
                    continue

            out = []
            for app_id, running in sorted(running_apps.items()):
                desc = apps.get(app_id)
                out.append(
                    {
                        "app_id": app_id,
                        "name": getattr(desc, "display_name", None) or app_id,
                        "active": app_id == active_app_id,
                        "background_enabled": bool(getattr(running, "background_enabled", False)),
                        "background_tasks": int(task_counts.get(app_id, 0)),
                    }
                )
            return out

        return self._host_call(_snapshot)

    def _kill_app(self, app_id: str) -> tuple[bool, Any]:
        app_id = str(app_id or "").strip()
        if not app_id:
            return False, "app id is required"

        def _kill(host):
            running_apps = getattr(host, "_running_apps", {}) or {}
            if app_id not in running_apps:
                return {"killed": False, "reason": "not running"}
            terminate = getattr(host, "_terminate_app", None)
            if not callable(terminate):
                return {"killed": False, "reason": "host cannot terminate apps"}
            terminate(app_id)
            return {"killed": True, "app_id": app_id}

        return self._host_call(_kill)

    def _build_runtime_namespace(self) -> dict[str, Any]:
        host = self.manager.host_window
        recovery_info = self.manager.recovery_info
        namespace = {
            "manager": self.manager,
            "service": self.manager,
            "host": host,
            "recovery_info": recovery_info,
            "base_dir": self.manager.base_dir,
            "Path": Path,
            "os": os,
            "sys": sys,
            "platform": platform,
            "subprocess": subprocess,
            "psutil": psutil,
            "paramiko": paramiko,
        }
        namespace.update(self._python_locals)
        return namespace

    def _cmd_install(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return
        if not parts:
            self.writeln("usage: install <path-to-package.pkg>")
            return

        package_path = Path(parts[0]).expanduser()
        if not package_path.is_absolute():
            package_path = self.manager.base_dir / package_path
        try:
            package_path = package_path.resolve()
            info = self._install_pkg_file(package_path)
            self._refresh_host_app_registry()
        except Exception as exc:
            self.writeln(f"install failed: {exc}")
            return

        action = "replaced" if info.get("replace") else "installed"
        self.writeln(f"{action}: {info.get('app_id')} ({info.get('display_name')})")
        self.writeln(f"location: {info.get('installed_to')}")

    def _cmd_uninstall(self, arg_text: str) -> None:
        try:
            raw_parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return

        keep_data = False
        parts: list[str] = []
        for part in raw_parts:
            if part == "--keep-data":
                keep_data = True
            else:
                parts.append(part)
        if not parts:
            self.writeln("usage: uninstall <app_id> [--keep-data]")
            return

        app_id = parts[0]
        ok, payload = self._host_call(lambda host: self._uninstall_user_app(app_id, keep_data=keep_data, host=host), timeout=10.0)
        if not ok and self.manager.host_window is None:
            try:
                payload = self._uninstall_user_app(app_id, keep_data=keep_data, host=None)
                ok = True
            except Exception as exc:
                payload = str(exc)

        if not ok:
            self.writeln(f"uninstall failed: {payload}")
            return

        self.writeln(f"uninstalled: {payload.get('app_id')} ({payload.get('display_name')})")
        self.writeln(f"removed app: {payload.get('removed_app')}")
        self.writeln("app data: kept" if payload.get("kept_data") else ("app data: removed" if payload.get("removed_data") else "app data: none"))

    def _cmd_running(self, *, background_only: bool = False) -> None:
        ok, payload = self._running_app_snapshot()
        if not ok:
            self.writeln(f"running apps unavailable: {payload}")
            return

        apps = list(payload or [])
        if background_only:
            apps = [item for item in apps if not bool(item.get("active"))]
        if not apps:
            self.writeln("no background apps" if background_only else "no running apps")
            return

        for item in apps:
            flags: list[str] = []
            if item.get("active"):
                flags.append("active")
            if item.get("background_enabled"):
                flags.append("background")
            task_count = int(item.get("background_tasks") or 0)
            if task_count:
                flags.append(f"{task_count} task{'s' if task_count != 1 else ''}")
            suffix = f" [{' | '.join(flags)}]" if flags else ""
            self.writeln(f"{item.get('app_id')}: {item.get('name')}{suffix}")

    def _cmd_bgapps(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return
        if parts and parts[0] == "kill":
            if len(parts) < 2:
                self.writeln("usage: bgapps kill <app_id>")
                return
            ok, snapshot = self._running_app_snapshot()
            if ok:
                active_ids = {str(item.get("app_id")) for item in snapshot or [] if bool(item.get("active"))}
                if parts[1] in active_ids:
                    self.writeln(f"{parts[1]} is foreground; use 'kill {parts[1]}' to terminate it anyway")
                    return
            self._cmd_kill(parts[1])
            return
        self._cmd_running(background_only=True)

    def _cmd_kill(self, app_id: str) -> None:
        app_id = str(app_id or "").strip()
        if not app_id:
            self.writeln("usage: kill <app_id>")
            return
        ok, payload = self._kill_app(app_id)
        if not ok:
            self.writeln(f"kill failed: {payload}")
            return
        if payload.get("killed"):
            self.writeln(f"kill requested: {app_id}")
        else:
            self.writeln(f"not killed: {app_id} ({payload.get('reason')})")

    def _collect_telephony_status(self) -> dict[str, Any]:
        modem = telephony_hal.get_modem()
        signal = modem.get_signal_strength()
        serving_cell = modem.get_serving_cell()
        return {
            "driver": modem.__class__.__name__,
            "signal": signal,
            "active_call": modem.get_active_call(),
            "sim": modem.get_sim_info(),
            "serving_cell": serving_cell,
            "neighboring_cells": modem.get_neighboring_cells(),
        }

    def _collect_media_status(self) -> dict[str, Any]:
        host = self.manager.host_window
        if host is None:
            return {"active_session": None}
        getter = getattr(host, "get_active_media_session", None)
        session = getter() if callable(getter) else None
        return {"active_session": session}

    def _media_debug_snapshot(self, host) -> dict[str, Any]:
        manager = getattr(host, "media_sessions", None)
        if manager is None:
            return {
                "active_session": None,
                "sessions": [],
                "session_order": [],
                "callbacks": {},
            }

        sessions_map = getattr(manager, "_sessions", {}) or {}
        callbacks_map = getattr(manager, "_callbacks", {}) or {}
        order = list(getattr(manager, "_session_order", []) or [])
        active = None
        try:
            active = manager.active_session()
        except Exception:
            active = None

        sessions = []
        for app_id, session in sorted(sessions_map.items()):
            sessions.append(_json_safe(session))

        callbacks: dict[str, list[str]] = {}
        for app_id, callbacks_for_app in callbacks_map.items():
            callbacks[str(app_id)] = sorted(str(command) for command in (callbacks_for_app or {}).keys())

        return {
            "active_session": active,
            "sessions": sessions,
            "session_order": order,
            "callbacks": callbacks,
        }

    def _parse_key_value_payload(self, values: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for value in values:
            if "=" not in value:
                payload[str(value)] = True
                continue
            key, raw = value.split("=", 1)
            key = key.strip()
            if not key:
                continue
            lowered = raw.strip().lower()
            if lowered in {"true", "yes", "on"}:
                payload[key] = True
            elif lowered in {"false", "no", "off"}:
                payload[key] = False
            else:
                try:
                    payload[key] = int(raw)
                except Exception:
                    try:
                        payload[key] = float(raw)
                    except Exception:
                        payload[key] = raw
        return payload

    def _cmd_media(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return

        action = (parts[0].lower() if parts else "list")
        args = parts[1:] if parts else []

        if action in {"list", "sessions", "active", "callbacks"}:
            ok, payload = self._host_call(lambda host: self._media_debug_snapshot(host))
            if not ok:
                self.writeln(f"media unavailable: {payload}")
                return

            if action == "active":
                self.writeln(_json_dumps(payload.get("active_session")))
                return
            if action == "callbacks":
                self.writeln(_json_dumps(payload.get("callbacks", {})))
                return
            self.writeln(_json_dumps(payload))
            return

        if action == "inspect":
            if not args:
                self.writeln("usage: media inspect <app_id>")
                return
            app_id = args[0]

            def _inspect(host):
                snapshot = self._media_debug_snapshot(host)
                sessions = snapshot.get("sessions") or []
                for session in sessions:
                    if str(session.get("app_id", "")) == app_id:
                        active_session = snapshot.get("active_session")
                        return {
                            "session": session,
                            "callbacks": (snapshot.get("callbacks", {}) or {}).get(app_id, []),
                            "active": bool(getattr(active_session, "app_id", "") == app_id),
                        }
                return None

            ok, payload = self._host_call(_inspect)
            if not ok:
                self.writeln(f"media unavailable: {payload}")
                return
            if payload is None:
                self.writeln(f"media session not found: {app_id}")
                return
            self.writeln(_json_dumps(payload))
            return

        if action in {"command", "send"}:
            if not args:
                self.writeln("usage: media command <command> [app_id] [key=value ...]")
                return
            command = args[0]
            app_id = None
            payload_args = args[1:]
            if payload_args and "=" not in payload_args[0]:
                app_id = payload_args[0]
                payload_args = payload_args[1:]
            payload = self._parse_key_value_payload(payload_args)
            ok, result = self._host_call(lambda host: bool(host.send_media_command(command, app_id=app_id, **payload)))
            self.writeln("ok" if ok and result else f"failed: {result}")
            return

        if action in getattr(media_hal, "MEDIA_COMMANDS", set()):
            app_id = args[0] if args and "=" not in args[0] else None
            payload_args = args[1:] if app_id else args
            payload = self._parse_key_value_payload(payload_args)
            ok, result = self._host_call(lambda host: bool(host.send_media_command(action, app_id=app_id, **payload)))
            self.writeln("ok" if ok and result else f"failed: {result}")
            return

        if action == "clear":
            if not args:
                self.writeln("usage: media clear <app_id|all>")
                return
            target = args[0]

            def _clear(host):
                manager = getattr(host, "media_sessions", None)
                if manager is None:
                    return {"cleared": []}
                if target == "all":
                    app_ids = list((getattr(manager, "_sessions", {}) or {}).keys())
                else:
                    app_ids = [target]
                for app_id in app_ids:
                    manager.clear_session(app_id)
                return {"cleared": app_ids}

            ok, payload = self._host_call(_clear)
            self.writeln(_json_dumps(payload) if ok else f"failed: {payload}")
            return

        if action == "fake":
            app_id = args[0] if args else "kangel.debug"
            title = " ".join(args[1:]).strip() or "KAngel Debug Track"

            def _fake_callback(command: str = "", **payload) -> None:
                self.manager._broadcast(
                    f"[KAngel media debug] command={command or '(callback)'} "
                    f"app_id={app_id} payload={_json_dumps(payload).strip()}"
                )

            def _fake(host):
                host.set_media_session(
                    app_id=app_id,
                    title=title,
                    artist="KAngel",
                    album="Debug Session",
                    position_ms=0,
                    duration_ms=180000,
                    playback_state="playing",
                    controls={"*": _fake_callback},
                )
                return host.get_active_media_session()

            ok, payload = self._host_call(_fake)
            self.writeln(_json_dumps(payload) if ok else f"failed: {payload}")
            return

        self.writeln("usage: media [list|active|callbacks|inspect|command|clear|fake]")

    def _cmd_button(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return
        if not parts:
            self.writeln("usage: button <home|power>")
            return

        action = parts[0].lower()
        if action not in {"home", "power"}:
            self.writeln("usage: button <home|power>")
            return

        def _press(host):
            handler_name = "_handle_home_button" if action == "home" else "_handle_power_button"
            handler = getattr(host, handler_name, None)
            if callable(handler):
                handler()
                return True
            if action == "home":
                fallback = getattr(host, "go_home", None)
            else:
                fallback = getattr(host, "lock_device", None)
            if callable(fallback):
                fallback()
                return True
            return False

        ok, payload = self._host_call(_press)
        self.writeln(f"{action} button pressed" if ok and payload else f"button press failed: {payload}")

    def _default_screenshot_path(self) -> Path:
        state_dir = self.manager._state_dir()
        screenshots_dir = state_dir / "Screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        return screenshots_dir / f"window_{timestamp}.png"

    def _cmd_screenshot(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return

        if parts:
            output_path = Path(parts[0]).expanduser()
            if not output_path.is_absolute():
                output_path = self.manager.base_dir / output_path
        else:
            output_path = self._default_screenshot_path()

        if output_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            output_path = output_path.with_suffix(".png")

        def _capture(host):
            target = getattr(host, "root", None) or host
            grab = getattr(target, "grab", None)
            if not callable(grab):
                raise RuntimeError("host window cannot be grabbed")
            pixmap = grab()
            if pixmap is None or pixmap.isNull():
                raise RuntimeError("screenshot capture returned a blank pixmap")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            ok = bool(pixmap.save(str(output_path)))
            if not ok:
                raise RuntimeError(f"failed to save screenshot to {output_path}")
            return {
                "path": str(output_path),
                "width": int(pixmap.width()),
                "height": int(pixmap.height()),
            }

        ok, payload = self._host_call(_capture, timeout=10.0)
        if not ok:
            self.writeln(f"screenshot failed: {payload}")
            return
        self.writeln(f"screenshot saved: {payload.get('path')} ({payload.get('width')}x{payload.get('height')})")

    def _collect_status_topic(self, topic: str) -> Any:
        topic = str(topic or "").strip().lower()
        if topic == "battery":
            return battery_hal.get_battery_info()
        if topic == "telephony":
            return self._collect_telephony_status()
        if topic == "audio":
            return audio_hal.get_audio_info()
        if topic == "display":
            return display_hal.get_display_info()
        if topic == "sensors":
            return sensors_hal.get_sensors_info()
        if topic == "location":
            return location_hal.get_location_info()
        if topic in {"thermal", "thermals"}:
            return thermals_hal.get_thermal_info()
        if topic == "wifi":
            return {
                "info": wifi_hal.get_wifi_info(),
                "profiles": wifi_hal.list_wifi_profiles(),
                "networks": wifi_hal.scan_wifi_networks(),
            }
        if topic == "vibration":
            return vibration_hal.get_vibration_info()
        if topic == "media":
            return self._collect_media_status()
        raise ValueError(f"unknown status topic: {topic}")

    def _cmd_status(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return
        topics = parts or ["all"]
        available = ["battery", "telephony", "audio", "display", "sensors", "location", "thermal", "wifi", "vibration", "media"]

        def _collect() -> Any:
            if len(topics) == 1 and topics[0].lower() == "all":
                return {topic: self._collect_status_topic(topic) for topic in available}
            return {topic: self._collect_status_topic(topic) for topic in topics}

        ok, payload = self._system_call(_collect, timeout=10.0)
        if not ok:
            self.writeln(f"status unavailable: {payload}")
            return
        self.writeln(_json_dumps(payload))

    def _cmd_control(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return
        if len(parts) < 2:
            self.writeln("usage: control <audio|display|telephony|wifi|vibration|device> <action> [value]")
            return

        domain = parts[0].lower()
        action = parts[1].lower()
        args = parts[2:]

        try:
            if domain == "audio":
                self._control_audio(action, args)
                return
            if domain == "display":
                self._control_display(action, args)
                return
            if domain == "telephony":
                self._control_telephony(action, args)
                return
            if domain == "wifi":
                self._control_wifi(action, args)
                return
            if domain == "vibration":
                self._control_vibration(action, args)
                return
            if domain == "device":
                self._control_device(action, args)
                return
        except Exception as exc:
            self.writeln(f"control failed: {exc}")
            return

        self.writeln(f"unknown control domain: {domain}")

    def _control_audio(self, action: str, args: list[str]) -> None:
        if action in {"info", "status"}:
            self._cmd_status("audio")
            return
        if action == "devices":
            self.writeln(_json_dumps(audio_hal.list_audio_output_devices()))
            return
        if action == "volume":
            if not args:
                self.writeln("usage: control audio volume <0-100>")
                return
            ok, payload = self._host_method_or_fallback("set_audio_volume", audio_hal.set_volume, int(args[0]))
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action == "mute":
            if not args:
                self.writeln("usage: control audio mute <on|off>")
                return
            enabled = _parse_enabled_token(args[0])
            if enabled is None:
                self.writeln("usage: control audio mute <on|off>")
                return
            ok, payload = self._host_method_or_fallback("set_audio_muted", audio_hal.set_muted, enabled)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action == "output":
            if not args:
                self.writeln("usage: control audio output <device_id>")
                return
            ok, payload = self._host_method_or_fallback("set_audio_output_device", audio_hal.set_output_device, args[0])
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        self.writeln("audio actions: info, devices, volume, mute, output")

    def _control_display(self, action: str, args: list[str]) -> None:
        if action in {"info", "status"}:
            self._cmd_status("display")
            return
        if action == "brightness":
            if not args:
                self.writeln("usage: control display brightness <0-100>")
                return
            ok, payload = self._system_call(lambda: display_hal.set_brightness(int(args[0])))
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action in {"auto", "auto-brightness", "autobrightness"}:
            if not args:
                self.writeln("usage: control display auto-brightness <on|off>")
                return
            enabled = _parse_enabled_token(args[0])
            if enabled is None:
                self.writeln("usage: control display auto-brightness <on|off>")
                return
            ok, payload = self._system_call(lambda: display_hal.set_auto_brightness(enabled))
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        self.writeln("display actions: info, brightness, auto-brightness")

    def _control_telephony(self, action: str, args: list[str]) -> None:
        if action in {"info", "status"}:
            self._cmd_status("telephony")
            return

        def _with_modem(fn):
            return self._system_call(lambda: fn(telephony_hal.get_modem()), timeout=10.0)

        if action == "dial":
            if not args:
                self.writeln("usage: control telephony dial <number>")
                return
            ok, payload = _with_modem(lambda modem: modem.dial(args[0]) or True)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action in {"hangup", "hang-up"}:
            ok, payload = _with_modem(lambda modem: modem.hang_up() or True)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action in {"sms", "text"}:
            if len(args) < 2:
                self.writeln("usage: control telephony sms <peer> <message>")
                return
            peer = args[0]
            body = " ".join(args[1:])
            ok, payload = _with_modem(lambda modem: modem.send_text(peer, body))
            self.writeln(_json_dumps(payload) if ok and payload else f"failed: {payload}")
            return
        if action == "incoming-call":
            if not args:
                self.writeln("usage: control telephony incoming-call <number>")
                return
            ok, payload = _with_modem(
                lambda modem: modem.simulate_incoming_call(args[0])
                if callable(getattr(modem, "simulate_incoming_call", None))
                else None
            )
            self.writeln(_json_dumps(payload) if ok and payload else f"failed: {payload or 'unsupported'}")
            return
        self.writeln("telephony actions: info, dial, hangup, sms, incoming-call")

    def _control_wifi(self, action: str, args: list[str]) -> None:
        if action in {"info", "status"}:
            self._cmd_status("wifi")
            return
        if action == "add":
            if not args:
                self.writeln("usage: control wifi add <ssid> [password]")
                return
            password = args[1] if len(args) > 1 else None
            ok, payload = self._host_method_or_fallback("add_wifi_profile", wifi_hal.add_wifi_profile, args[0], password=password, secure=(True if password else None))
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action in {"delete", "remove"}:
            if not args:
                self.writeln("usage: control wifi delete <ssid>")
                return
            ok, payload = self._host_method_or_fallback("delete_wifi_profile", wifi_hal.delete_wifi_profile, args[0])
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        self.writeln("wifi actions: info, add, delete")

    def _control_vibration(self, action: str, args: list[str]) -> None:
        if action in {"info", "status"}:
            self._cmd_status("vibration")
            return
        if action == "vibrate":
            duration = int(args[0]) if args else 250
            intensity = float(args[1]) if len(args) > 1 else None
            ok, payload = self._system_call(lambda: vibration_hal.vibrate(duration, intensity=intensity))
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action == "stop":
            ok, payload = self._system_call(vibration_hal.stop_vibration)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        self.writeln("vibration actions: info, vibrate, stop")

    def _control_device(self, action: str, args: list[str]) -> None:
        if action == "lock":
            ok, payload = self._host_call(lambda host: getattr(host, "lock_device")() or True)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action == "unlock":
            ok, payload = self._host_call(lambda host: getattr(host, "unlock_device")() or True)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        if action == "home":
            ok, payload = self._host_call(lambda host: getattr(host, "go_home")() or True)
            self.writeln("ok" if ok and payload else f"failed: {payload}")
            return
        self.writeln("device actions: lock, unlock, home")

    def _cmd_help(self) -> None:
        self.writeln("  help               Show this command list")
        self.writeln("  info [os|device]   Show runtime, OS build, and device config")
        self.writeln("  recovery           Show current panic details")
        self.writeln("  apps               List discovered apps")
        self.writeln("  launch <app_id>    Launch an app on the UI thread")
        self.writeln("  install <pkg>      Install a user app package")
        self.writeln("  uninstall <app_id> Uninstall a user app")
        self.writeln("  running            List running apps")
        self.writeln("  bgapps             List background apps")
        self.writeln("  kill <app_id>      Terminate a running app")
        self.writeln("  logs               List recent log files")
        self.writeln("  logs <name> [n]    Tail a log file")
        self.writeln("  logstream [name]   Follow a log live (Ctrl-C stops)")
        self.writeln("  media ...          Inspect/debug media sessions and commands")
        self.writeln("  button <name>      Simulate HOME or POWER button press")
        self.writeln("  screenshot [path]  Capture the current shell window")
        self.writeln("  status [topic]     Show battery, telephony, audio, and HAL data")
        self.writeln("  control <area> ... Control audio, display, telephony, Wi-Fi, vibration")
        self.writeln("  crash [id]         List or inspect app crashes")
        self.writeln("  pdb [id]           Debug the last app crash in this SSH session")
        self.writeln("  exec <command>     Run one shell command and print output")
        self.writeln("  shell              Enter a raw local shell session")
        self.writeln("  py <code>          Execute Python in-process")
        self.writeln("  history [n]        Show recent KAngel commands")
        self.writeln("  clear              Clear the terminal screen")
        self.writeln("  exit               Close the KAngel session")

    def _device_config_summary_lines(self, device) -> list[str]:
        drivers = getattr(device, "drivers", {}) or {}
        driver_text = ", ".join(f"{key}={value}" for key, value in sorted(drivers.items())) or "(none)"
        lines = [
            f"device manufacturer: {getattr(device, 'manufacturer', '') or '(unknown)'}",
            f"device model: {getattr(device, 'model', '') or '(unknown)'}",
            f"device model name: {getattr(device, 'model_name', '') or '(unknown)'}",
            f"device serial: {getattr(device, 'serial_number', '') or '(unset)'}",
            f"device hardware revision: {getattr(device, 'hardware_revision', '') or '(unset)'}",
            f"device has hardware home: {bool(getattr(device, 'has_hw_home', False))}",
            f"device drivers: {driver_text}",
        ]
        identifiers = []
        for label, attr in (("imei", "imei"), ("wifi mac", "wifi_mac"), ("bluetooth mac", "bluetooth_mac")):
            value = str(getattr(device, attr, "") or "").strip()
            if value:
                identifiers.append(f"{label}={value}")
        if identifiers:
            lines.append(f"device identifiers: {', '.join(identifiers)}")
        return lines

    def _os_config_summary_lines(self, build) -> list[str]:
        builder = ""
        builder_user = str(getattr(build, "builder_username", "") or "")
        builder_host = str(getattr(build, "builder_hostname", "") or "")
        if builder_user or builder_host:
            builder = f"{builder_user}@{builder_host}".strip("@")
        return [
            f"os name: {getattr(build, 'os_name', '') or '(unknown)'}",
            f"os version: {getattr(build, 'os_version', '') or '(unknown)'}",
            f"os build number: {getattr(build, 'build_number', '')}",
            f"os build id: {getattr(build, 'build_id', '') or '(unset)'}",
            f"os channel: {getattr(build, 'channel', '') or '(unset)'}",
            f"os builder: {builder or '(unset)'}",
            f"os build datetime: {getattr(build, 'build_datetime', '') or '(unset)'}",
        ]

    def _cmd_info(self, arg_text: str = "") -> None:
        arg_text = str(arg_text or "").strip().lower()
        build = OSBuildConfigStore(base_dir=self.manager.base_dir).load()
        device = DeviceConfigStore(base_dir=self.manager.base_dir).load()

        if arg_text in {"os", "osconfig", "build"}:
            self.writeln(_json_dumps(build))
            return
        if arg_text in {"device", "deviceconfig", "hardware", "drivers"}:
            self.writeln(_json_dumps(device))
            return
        if arg_text and arg_text not in {"all", "summary"}:
            self.writeln("usage: info [os|device|all]")
            return

        lines = [
            f"user: {self.username}",
            f"host user: {getpass.getuser()}",
            f"mode: {'recovery' if self.manager.recovery_info else 'normal'}",
            f"channel: {getattr(build, 'channel', '')}",
            f"build: {getattr(build, 'build_id', '')}",
            f"python: {platform.python_version()} ({platform.python_implementation()})",
            f"platform: {platform.platform(aliased=True)}",
            f"kangel: {'listening' if self.manager.is_running() else 'stopped'} on tcp/{self.manager.port}",
            f"addresses: {', '.join(self.manager.addresses()) or '(none)'}",
        ]

        lines.extend(self._os_config_summary_lines(build))
        lines.extend(self._device_config_summary_lines(device))

        ok, state = self._host_call(
            lambda host: {
                "active_app_id": getattr(host, "active_app_id", None),
                "locked": bool(getattr(host, "_locked", False)),
                "setup_completed": bool(getattr(host, "is_setup_completed", lambda: False)()),
                "app_count": len(getattr(host, "apps", {}) or {}),
            }
        )
        if ok and isinstance(state, dict):
            lines.extend(
                [
                    f"active app: {state.get('active_app_id') or '(none)'}",
                    f"locked: {state.get('locked')}",
                    f"setup completed: {state.get('setup_completed')}",
                    f"registered apps: {state.get('app_count')}",
                ]
            )
        else:
            lines.append(f"ui state: {state}")

        for line in lines:
            self.writeln(line)

    def _cmd_recovery(self) -> None:
        info = self.manager.recovery_info
        if not info:
            self.writeln("recovery mode is not active")
            return
        self.writeln(json.dumps(info, indent=2, sort_keys=True))

    def _cmd_apps(self) -> None:
        ok, payload = self._host_call(
            lambda host: [
                {
                    "id": app_id,
                    "name": getattr(desc, "display_name", "") or app_id,
                    "hidden": bool(getattr(desc, "hidden", False)),
                }
                for app_id, desc in sorted((getattr(host, "apps", {}) or {}).items())
            ]
        )
        if not ok:
            self.writeln(f"apps unavailable: {payload}")
            return
        if not payload:
            self.writeln("no apps registered")
            return
        for item in payload:
            hidden_suffix = " [hidden]" if item.get("hidden") else ""
            self.writeln(f"{item.get('id')}: {item.get('name')}{hidden_suffix}")

    def _cmd_launch(self, app_id: str) -> None:
        app_id = str(app_id or "").strip()
        if not app_id:
            self.writeln("usage: launch <app_id>")
            return
        ok, payload = self._host_call(
            lambda host: (
                app_id in getattr(host, "apps", {})
                and host.launch_app(app_id) is None
            )
        )
        if ok and payload:
            self.writeln(f"launch requested: {app_id}")
        elif ok:
            self.writeln(f"unknown app: {app_id}")
        else:
            self.writeln(f"launch failed: {payload}")

    def _resolve_log_path(self, token: str) -> Path | None:
        logs_dir = self.manager.base_dir / "logs"
        files = sorted((p for p in logs_dir.glob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        if not token or token == "latest":
            return files[0] if files else None
        candidate = logs_dir / token
        if candidate.exists():
            return candidate
        for item in files:
            if item.name == token:
                return item
        return None

    def _cmd_logs(self, arg_text: str) -> None:
        arg_text = str(arg_text or "").strip()
        logs_dir = self.manager.base_dir / "logs"
        if not arg_text:
            files = sorted((p for p in logs_dir.glob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
            if not files:
                self.writeln("no log files found")
                return
            for item in files:
                self.writeln(f"{item.name} ({item.stat().st_size} bytes)")
            return

        parts = shlex.split(arg_text)
        if parts and parts[0] in {"-f", "--follow", "follow"}:
            self._cmd_logstream(arg_text)
            return
        token = parts[0] if parts else "latest"
        lines = 80
        if len(parts) > 1:
            try:
                lines = max(1, min(500, int(parts[1])))
            except Exception:
                pass

        path = self._resolve_log_path(token)
        if path is None:
            self.writeln(f"log not found: {token}")
            return
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            self.writeln(f"failed to read {path.name}: {exc}")
            return
        self.writeln(f"==> {path.name} <==")
        for line in content[-lines:]:
            self.writeln(line)

    def _cmd_logstream(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return

        token = "latest"
        lines = 80
        if parts:
            if parts[0] in {"-f", "--follow", "follow"}:
                parts = parts[1:]
            if parts:
                token = parts[0]
            if len(parts) > 1:
                try:
                    lines = max(0, min(1000, int(parts[1])))
                except Exception:
                    self.writeln(f"invalid line count: {parts[1]}")
                    return

        path = self._resolve_log_path(token)
        if path is None:
            self.writeln(f"log not found: {token}")
            return

        self.writeln(f"streaming {path.name}; press Ctrl-C to stop")
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines > 0:
                self.writeln(f"==> {path.name} <==")
                for line in content[-lines:]:
                    self.writeln(line)
        except Exception as exc:
            self.writeln(f"failed to read {path.name}: {exc}")
            return

        current_path = path
        try:
            offset = current_path.stat().st_size
        except Exception:
            offset = 0

        previous_timeout = self._set_channel_timeout(0.25)
        try:
            while True:
                try:
                    data = self.channel.recv(1)
                except socket.timeout:
                    data = b""
                except Exception:
                    break
                if data == b"\x03":
                    self.write("^C\n")
                    break
                if data in {b"q", b"Q"}:
                    break

                if token == "latest":
                    latest = self._resolve_log_path("latest")
                    if latest is not None and latest != current_path:
                        current_path = latest
                        offset = 0
                        self.writeln(f"==> {current_path.name} <==")

                try:
                    size = current_path.stat().st_size
                except Exception:
                    time.sleep(0.2)
                    continue
                if size < offset:
                    offset = 0
                    self.writeln(f"==> {current_path.name} truncated <==")
                if size > offset:
                    try:
                        with current_path.open("r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(offset)
                            chunk = fh.read()
                            offset = fh.tell()
                        if chunk:
                            self.write(chunk if chunk.endswith("\n") else chunk + "\n")
                    except Exception as exc:
                        self.writeln(f"stream read failed: {exc}")
                        break
                time.sleep(0.15)
        finally:
            self._restore_channel_timeout(previous_timeout)
            self.writeln("log stream ended")

    def _cmd_crash(self, arg_text: str) -> None:
        try:
            parts = shlex.split(str(arg_text or ""))
        except Exception as exc:
            self.writeln(f"invalid arguments: {exc}")
            return

        records = self.manager.crash_records()
        if not records:
            self.writeln("no crashes recorded")
            return

        if not parts:
            for record in records[-12:]:
                self.writeln(
                    f"#{record.get('id')} {record.get('timestamp')} "
                    f"{record.get('app_id') or '(unknown)'} "
                    f"{record.get('exception_type')}: {record.get('message')}"
                )
            self.writeln("use 'crash <id>' for details or 'pdb <id>' for a debugger")
            return

        record = self.manager.resolve_crash_record(parts[0])
        if record is None:
            self.writeln(f"crash not found: {parts[0]}")
            return

        self.writeln(f"crash #{record.get('id')}")
        self.writeln(f"time: {record.get('timestamp')}")
        self.writeln(f"app: {record.get('app_name') or record.get('app_id')} ({record.get('app_id')})")
        self.writeln(f"exception: {record.get('exception_type')}: {record.get('message')}")
        if record.get("report_path"):
            self.writeln(f"report: {record.get('report_path')}")
        formatted = str(record.get("formatted") or "").rstrip()
        if formatted:
            self.writeln("traceback:")
            self.write(formatted if formatted.endswith("\n") else formatted + "\n")

    class _PdbOutput:
        def __init__(self, session: "KAngelSession") -> None:
            self.session = session

        def write(self, text: str) -> int:
            value = str(text or "")
            self.session.write(value)
            return len(value)

        def flush(self) -> None:
            return None

    class _PdbInput:
        def __init__(self, session: "KAngelSession") -> None:
            self.session = session

        def readline(self) -> str:
            text = ""
            while True:
                try:
                    chunk = self.session.channel.recv(1)
                except Exception:
                    return "q\n"
                if not chunk:
                    return "q\n"
                if chunk in (b"\r", b"\n"):
                    self.session.write("\n")
                    return text + "\n"
                if chunk == b"\x03":
                    self.session.write("^C\n")
                    return "q\n"
                if chunk in (b"\x08", b"\x7f"):
                    if text:
                        text = text[:-1]
                        self.session.write("\b \b")
                    continue
                try:
                    decoded = chunk.decode("utf-8", errors="replace")
                except Exception:
                    decoded = ""
                if not decoded or not decoded.isprintable():
                    continue
                text += decoded
                self.session.write(decoded)

    def _cmd_pdb(self, arg_text: str) -> None:
        token = str(arg_text or "").strip() or "latest"
        record = self.manager.resolve_crash_record(token)
        if record is None:
            self.writeln(f"crash not found: {token}")
            return
        tb = record.get("traceback")
        if tb is None:
            self.writeln(f"crash #{record.get('id')} has no traceback object")
            return

        self.writeln(f"entering pdb for crash #{record.get('id')} ({record.get('app_id') or 'unknown'})")
        self.writeln("type 'q' to leave pdb and return to KAngel")
        previous_timeout = self._set_channel_timeout(None)
        try:
            debugger = pdb.Pdb(stdin=self._PdbInput(self), stdout=self._PdbOutput(self))
            debugger.reset()
            debugger.interaction(None, tb)
        except Exception:
            self.writeln(traceback.format_exc().rstrip())
        finally:
            self._restore_channel_timeout(previous_timeout)
            self.writeln("left pdb")

    def _cmd_history(self, arg_text: str) -> None:
        arg_text = str(arg_text or "").strip()
        limit = 20
        if arg_text:
            try:
                limit = max(1, min(KANGEL_HISTORY_LIMIT, int(arg_text)))
            except Exception:
                self.writeln(f"invalid history count: {arg_text}")
                return
        if not self._history:
            self.writeln("history is empty")
            return
        start = max(0, len(self._history) - limit)
        for idx, item in enumerate(self._history[start:], start=start + 1):
            self.writeln(f"{idx:>4}  {item}")

    def _run_shell_command(self, command: str) -> tuple[int, str]:
        if os.name == "nt":
            argv = ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command]
        else:
            argv = [os.environ.get("SHELL") or "/bin/sh", "-lc", command]
        proc = subprocess.run(
            argv,
            cwd=str(self.manager.base_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = ""
        if proc.stdout:
            output = proc.stdout
        if proc.stderr:
            output = proc.stderr
        return int(proc.returncode), output

    def _cmd_exec(self, command: str) -> None:
        command = str(command or "").strip()
        if not command:
            self.writeln("usage: exec <command>")
            return
        rc, output = self._run_shell_command(command)
        if output:
            self.write(output if output.endswith("\n") else output + "\n")
        self.writeln(f"[exit {rc}]")

    def _build_shell_env(self) -> dict[str, str]:
        env = {str(k): str(v) for k, v in os.environ.items()}
        for key, value in self._env_requests.items():
            if key == "TERM" or key == "COLORTERM" or key == "LANG" or key.startswith("LC_"):
                env[str(key)] = str(value)
        env["TERM"] = str(self._env_requests.get("TERM") or self._pty_term or env.get("TERM") or "xterm-256color")
        return env

    def _channel_timeout(self) -> float:
        return 0.25

    def _set_channel_timeout(self, timeout: float | None) -> Any:
        getter = getattr(self.channel, "gettimeout", None)
        setter = getattr(self.channel, "settimeout", None)
        previous = None
        if callable(getter):
            try:
                previous = getter()
            except Exception:
                previous = None
        if callable(setter):
            try:
                setter(timeout)
            except Exception:
                pass
        return previous

    def _restore_channel_timeout(self, timeout: Any) -> None:
        setter = getattr(self.channel, "settimeout", None)
        if not callable(setter):
            return
        try:
            setter(timeout)
        except Exception:
            pass

    def _shell_closed_message(self, returncode: int | None) -> str:
        if returncode is None:
            return "shell closed"
        return f"shell closed [exit {returncode}]"

    def _cmd_shell_piped(self, argv: list[str]) -> None:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(self.manager.base_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self._build_shell_env(),
                text=False,
            )
        except Exception as exc:
            self.writeln(f"failed to start shell: {exc}")
            return

        stop = threading.Event()

        def _pump_stdout() -> None:
            try:
                while not stop.is_set():
                    chunk = proc.stdout.read(1024) if proc.stdout is not None else b""
                    if not chunk:
                        break
                    try:
                        self.channel.sendall(chunk)
                    except Exception:
                        break
            finally:
                stop.set()

        pump_thread = threading.Thread(target=_pump_stdout, name="KAngelShellPump", daemon=True)
        pump_thread.start()

        previous_timeout = self._set_channel_timeout(self._channel_timeout())
        try:
            while True:
                if stop.is_set() or proc.poll() is not None:
                    break
                try:
                    data = self.channel.recv(1024)
                except socket.timeout:
                    continue
                except Exception:
                    break
                if not data:
                    break
                if proc.stdin is None:
                    break
                proc.stdin.write(data)
                proc.stdin.flush()
        finally:
            self._restore_channel_timeout(previous_timeout)
            stop.set()
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                returncode = proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    returncode = proc.wait(timeout=2)
                except Exception:
                    returncode = proc.poll()
            self.writeln("")
            self.writeln(self._shell_closed_message(returncode))

    def _cmd_shell_posix_pty(self, argv: list[str]) -> None:
        if fcntl is None or select is None or termios is None:
            self._cmd_shell_piped(argv)
            return
        master_fd = None
        slave_fd = None
        proc = None
        stop = threading.Event()
        try:
            master_fd, slave_fd = os.openpty()
            _set_pty_window_size(slave_fd, self._pty_cols, self._pty_rows)

            def _preexec() -> None:
                os.setsid()
                if fcntl is not None and termios is not None and hasattr(termios, "TIOCSCTTY"):
                    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            proc = subprocess.Popen(
                argv,
                cwd=str(self.manager.base_dir),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=self._build_shell_env(),
                text=False,
                close_fds=True,
                preexec_fn=_preexec,
            )
        except Exception as exc:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except Exception:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
            self.writeln(f"failed to start shell: {exc}")
            return
        finally:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except Exception:
                    pass

        self._active_pty_master_fd = master_fd
        self.update_pty_size(self._pty_cols, self._pty_rows)

        def _pump_pty() -> None:
            try:
                while not stop.is_set():
                    readable, _, _ = select.select([master_fd], [], [], self._channel_timeout())
                    if not readable:
                        if proc.poll() is not None:
                            break
                        continue
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    try:
                        self.channel.sendall(chunk)
                    except Exception:
                        break
            finally:
                stop.set()

        pump_thread = threading.Thread(target=_pump_pty, name="KAngelShellPTYPump", daemon=True)
        pump_thread.start()

        previous_timeout = self._set_channel_timeout(self._channel_timeout())
        try:
            while True:
                if stop.is_set() or proc.poll() is not None:
                    break
                try:
                    data = self.channel.recv(1024)
                except socket.timeout:
                    continue
                except Exception:
                    break
                if not data:
                    break
                try:
                    os.write(master_fd, data)
                except OSError:
                    break
        finally:
            self._restore_channel_timeout(previous_timeout)
            stop.set()
            self._active_pty_master_fd = None
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
            try:
                returncode = proc.wait(timeout=2)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    returncode = proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        returncode = proc.wait(timeout=2)
                    except Exception:
                        returncode = proc.poll()
            self.writeln("")
            self.writeln(self._shell_closed_message(returncode))

    def _cmd_shell(self, arg_text: str) -> None:
        argv = shlex.split(arg_text) if arg_text.strip() else _default_shell_argv()
        self.writeln(f"entering shell: {' '.join(argv)}")
        self.writeln("type exit to return to KAngel and the Needy Streamer Overload shell")
        if os.name != "nt":
            self._cmd_shell_posix_pty(argv)
            return
        self._cmd_shell_piped(argv)

    def _cmd_py(self, code: str) -> None:
        code = str(code or "").strip()
        if not code:
            self.writeln("usage: py <python code>")
            return
        namespace = self._build_runtime_namespace()
        try:
            compiled = compile(code, "<kangel>", "eval")
        except SyntaxError:
            try:
                exec(compile(code, "<kangel>", "exec"), namespace, namespace)
                self._python_locals.update(namespace)
                self.writeln("ok")
            except Exception:
                self.writeln(traceback.format_exc().rstrip())
            return
        try:
            result = eval(compiled, namespace, namespace)
            namespace["_"] = result
            self._python_locals.update(namespace)
            self.writeln(repr(result))
        except Exception:
            self.writeln(traceback.format_exc().rstrip())

    def run_command(self, command: str) -> bool:
        raw = str(command or "").strip()
        if not raw:
            return True
        if raw in {"exit", "quit", "logout"}:
            return False
        if raw in {"help", "?"}:
            self._cmd_help()
            return True
        if raw == "info" or raw.startswith("info "):
            self._cmd_info(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "recovery":
            self._cmd_recovery()
            return True
        if raw == "apps":
            self._cmd_apps()
            return True
        if raw.startswith("launch "):
            self._cmd_launch(raw.partition(" ")[2])
            return True
        if raw == "install" or raw.startswith("install "):
            self._cmd_install(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "uninstall" or raw.startswith("uninstall "):
            self._cmd_uninstall(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "running":
            self._cmd_running(background_only=False)
            return True
        if raw == "bgapps" or raw.startswith("bgapps "):
            self._cmd_bgapps(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "kill" or raw.startswith("kill "):
            self._cmd_kill(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "logs" or raw.startswith("logs "):
            self._cmd_logs(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "logstream" or raw.startswith("logstream "):
            self._cmd_logstream(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "media" or raw.startswith("media "):
            self._cmd_media(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "button" or raw.startswith("button "):
            self._cmd_button(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "screenshot" or raw.startswith("screenshot "):
            self._cmd_screenshot(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "status" or raw.startswith("status "):
            self._cmd_status(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "control" or raw.startswith("control "):
            self._cmd_control(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "crash" or raw.startswith("crash "):
            self._cmd_crash(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "pdb" or raw.startswith("pdb "):
            self._cmd_pdb(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "history" or raw.startswith("history "):
            self._cmd_history(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw == "clear":
            self._clear_screen()
            return True
        if raw.startswith("exec "):
            self._cmd_exec(raw.partition(" ")[2])
            return True
        if raw.startswith("py "):
            self._cmd_py(raw.partition(" ")[2])
            return True
        if raw == "shell" or raw.startswith("shell "):
            self._cmd_shell(raw.partition(" ")[2] if " " in raw else "")
            return True
        if raw.startswith("!"):
            self._cmd_exec(raw[1:])
            return True
        self.writeln(f"unknown command: {raw}")
        self.writeln("type 'help' for a command list")
        return True

    def run_interactive(self) -> None:
        for line in KANGEL_WELCOME_LINES:
            self.writeln(line)
        self.writeln("type 'help' for commands")
        while True:
            line = self._readline(KANGEL_PROMPT)
            if line is None:
                return
            try:
                self._append_history_entry(line)
                if not self.run_command(line):
                    return
            except Exception:
                self.writeln(traceback.format_exc().rstrip())


class KAngelManager:
    def __init__(self, *, base_dir: Path, logger, port: int = KANGEL_PORT) -> None:
        self.base_dir = Path(base_dir)
        self.logger = logger
        self.port = int(port)
        self._enabled = False
        self._running = False
        self._lock = threading.RLock()
        self._server_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._host_key = None
        self.host_window: Any | None = None
        self.recovery_info: dict[str, Any] | None = None
        self._history_lock = threading.RLock()
        self._sessions_lock = threading.RLock()
        self._sessions: set[KAngelSession] = set()
        self._crash_lock = threading.RLock()
        self._crashes: list[dict[str, Any]] = []
        self._next_crash_id = 1

    def attach_host_window(self, host_window: Any | None) -> None:
        self.host_window = host_window

    def set_recovery_info(self, info: dict[str, Any] | None) -> None:
        self.recovery_info = dict(info or {}) if info else None

    def addresses(self) -> list[str]:
        return _collect_ip_addresses()

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._enabled),
            "running": bool(self._running),
            "port": int(self.port),
            "addresses": self.addresses(),
        }

    def is_running(self) -> bool:
        return bool(self._running)

    def ensure_started(self) -> bool:
        with self._lock:
            self._enabled = True
            if self._running:
                return True
            if paramiko is None:
                self.logger.warning("KAngel unavailable because paramiko is not installed")
                return False

            try:
                self._host_key = self._load_or_create_host_key()
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.bind(("0.0.0.0", self.port))
                self._server_socket.listen(8)
                self._server_socket.settimeout(1.0)
                self._stop_event.clear()
                self._accept_thread = threading.Thread(target=self._accept_loop, name="KAngelAccept", daemon=True)
                self._accept_thread.start()
                self._running = True
                self.logger.info("KAngel listening", extra={"port": self.port, "addresses": self.addresses()})
                return True
            except Exception:
                self.logger.exception("Failed to start KAngel")
                self._close_server_socket()
                self._running = False
                return False

    def stop(self) -> None:
        with self._lock:
            self._enabled = False
            self._running = False
            self._stop_event.set()
            self._close_server_socket()

    def update_enabled(self, enabled: bool) -> bool:
        if enabled:
            return self.ensure_started()
        self.stop()
        return True

    def _close_server_socket(self) -> None:
        sock = self._server_socket
        self._server_socket = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def _state_dir(self) -> Path:
        layout = get_user_data_layout(self.base_dir)
        layout.ensure_directories()
        key_dir = layout.data_system / "KAngel"
        key_dir.mkdir(parents=True, exist_ok=True)
        return key_dir

    def _host_key_path(self) -> Path:
        return self._state_dir() / KANGEL_HOST_KEY_NAME

    def _history_path(self) -> Path:
        return self._state_dir() / KANGEL_HISTORY_FILE_NAME

    def _load_history_unlocked(self) -> list[str]:
        try:
            raw = json.loads(self._history_path().read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        values = [str(item).strip() for item in raw if str(item).strip()]
        return values[-KANGEL_HISTORY_LIMIT:]

    def load_history(self) -> list[str]:
        with self._history_lock:
            return self._load_history_unlocked()

    def append_history_entry(self, command: str) -> None:
        value = str(command or "").strip()
        if not value:
            return
        with self._history_lock:
            history = self._load_history_unlocked()
            if history and history[-1] == value:
                return
            history.append(value)
            history = history[-KANGEL_HISTORY_LIMIT:]
            try:
                self._history_path().write_text(json.dumps(history, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _register_session(self, session: KAngelSession) -> None:
        with self._sessions_lock:
            self._sessions.add(session)

    def _unregister_session(self, session: KAngelSession) -> None:
        with self._sessions_lock:
            self._sessions.discard(session)

    def _broadcast(self, text: str) -> None:
        with self._sessions_lock:
            sessions = list(self._sessions)
        for session in sessions:
            try:
                session.write("\n" + str(text).rstrip() + "\n")
            except Exception:
                pass

    def record_app_crash(
        self,
        exc_type,
        exc,
        tb,
        *,
        app_id: str | None = None,
        app_name: str | None = None,
        report_path: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]:
        try:
            exception_type = getattr(exc_type, "__name__", str(exc_type))
        except Exception:
            exception_type = "Exception"
        try:
            formatted = "".join(traceback.format_exception(exc_type, exc, tb))
        except Exception:
            formatted = ""

        with self._crash_lock:
            crash_id = self._next_crash_id
            self._next_crash_id += 1
            record = {
                "id": crash_id,
                "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
                "app_id": str(app_id or ""),
                "app_name": str(app_name or app_id or ""),
                "exception_type": str(exception_type),
                "message": str(exc),
                "report_path": str(report_path) if report_path else "",
                "formatted": formatted,
                "exc_type": exc_type,
                "exception": exc,
                "traceback": tb,
            }
            self._crashes.append(record)
            self._crashes = self._crashes[-20:]

        summary = (
            f"[KAngel crash #{crash_id}] {record['app_id'] or '(unknown app)'} "
            f"{record['exception_type']}: {record['message']}\n"
            f"[KAngel] use 'crash {crash_id}' for details or 'pdb {crash_id}' for a debugger"
        )
        self._broadcast(summary)
        return record

    def crash_records(self) -> list[dict[str, Any]]:
        with self._crash_lock:
            return list(self._crashes)

    def resolve_crash_record(self, token: str | int | None = None) -> dict[str, Any] | None:
        with self._crash_lock:
            records = list(self._crashes)
        if not records:
            return None
        raw = str(token or "latest").strip().lower()
        if raw in {"", "latest", "last"}:
            return records[-1]
        try:
            wanted = int(raw.lstrip("#"))
        except Exception:
            return None
        for record in reversed(records):
            try:
                if int(record.get("id")) == wanted:
                    return record
            except Exception:
                continue
        return None

    def _load_or_create_host_key(self):
        key_path = self._host_key_path()
        if key_path.exists():
            return paramiko.RSAKey(filename=str(key_path))
        key = paramiko.RSAKey.generate(2048)
        key.write_private_key_file(str(key_path))
        return key

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            server_socket = self._server_socket
            if server_socket is None:
                return
            try:
                client, address = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            except Exception:
                self.logger.exception("KAngel accept failed")
                continue
            thread = threading.Thread(
                target=self._handle_client,
                args=(client, address),
                name="KAngelClient",
                daemon=True,
            )
            thread.start()

    def _handle_client(self, client: socket.socket, address) -> None:
        transport = None
        try:
            transport = paramiko.Transport(client)
            transport.add_server_key(self._host_key)
            server = _KAngelSSHServer()
            transport.start_server(server=server)
            channel = transport.accept(20)
            if channel is None:
                return
            if not server.event.wait(10):
                channel.sendall(b"KAngel session timed out waiting for a shell request.\r\n")
                return
            self.logger.info("KAngel client connected", extra={"address": str(address), "username": server.username})
            session = KAngelSession(
                self,
                channel,
                server.username,
                pty_term=server.pty_term,
                pty_cols=server.pty_cols,
                pty_rows=server.pty_rows,
                env_requests=server.env_requests,
            )
            server.pty_resize_handler = session.update_pty_size
            self._register_session(session)
            try:
                if server.exec_command is not None:
                    session.run_command(server.exec_command)
                    channel.send_exit_status(0)
                else:
                    session.run_interactive()
            finally:
                self._unregister_session(session)
        except Exception:
            self.logger.exception("KAngel client session failed", extra={"address": str(address)})
        finally:
            try:
                if transport is not None:
                    transport.close()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
