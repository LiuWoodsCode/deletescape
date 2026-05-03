import ctypes
import ctypes.util
import getpass
import inspect
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import threading
import traceback
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

from config import CONFIG_FILE_NAME, OSBuildConfigStore
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
    "logs",
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
        elif first == "logs":
            replacement, candidates = self._apply_completion_candidates(fragment, self._log_completion_candidates(fragment))
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

    def _cmd_help(self) -> None:
        self.writeln("  help               Show this command list")
        self.writeln("  info               Show device, build state")
        self.writeln("  recovery           Show current panie details")
        self.writeln("  apps               List discovered apps")
        self.writeln("  launch <app_id>    Launch an app on the UI thread")
        self.writeln("  logs               List recent log files")
        self.writeln("  logs <name> [n]    Tail a log file")
        self.writeln("  exec <command>     Run one shell command and print output")
        self.writeln("  shell              Enter a raw local shell session")
        self.writeln("  py <code>          Execute Python in-process")
        self.writeln("  history [n]        Show recent KAngel commands")
        self.writeln("  clear              Clear the terminal screen")
        self.writeln("  exit               Close the KAngel session")

    def _cmd_info(self) -> None:
        build = OSBuildConfigStore(base_dir=self.manager.base_dir).load()
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
        if raw == "info":
            self._cmd_info()
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
        if raw == "logs" or raw.startswith("logs "):
            self._cmd_logs(raw.partition(" ")[2] if " " in raw else "")
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
            if server.exec_command is not None:
                session.run_command(server.exec_command)
                channel.send_exit_status(0)
            else:
                session.run_interactive()
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
