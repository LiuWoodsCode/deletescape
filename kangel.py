

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


def authenticate_system_user(username: str, password: str) -> tuple[bool, str]:
    if not username:
        return False, "username is required"
    if password is None:
        return False, "password is required"

    if username == "sayori" and password == "justmonika": ## todo: this is horrible
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
    def __init__(self, manager: "KAngelManager", channel, username: str) -> None:
        self.manager = manager
        self.channel = channel
        self.username = str(username or "")
        self._python_locals: dict[str, Any] = {}

    def write(self, text: str) -> None:
        if not text:
            return
        try:
            self.channel.sendall(text.replace("\n", "\r\n"))
        except Exception:
            pass

    def writeln(self, text: str = "") -> None:
        self.write(text + "\n")

    def _readline(self, prompt: str = "") -> str | None:
        if prompt:
            self.write(prompt)
        data = bytearray()
        while True:
            try:
                chunk = self.channel.recv(1)
            except Exception:
                return None
            if not chunk:
                return None
            if chunk in (b"\r", b"\n"):
                self.write("\n")
                return data.decode("utf-8", errors="replace")
            if chunk in (b"\x08", b"\x7f"):
                if data:
                    data = data[:-1]
                    self.write("\b \b")
                continue
            if chunk == b"\x03":
                self.write("^C\n")
                return ""
            try:
                decoded = chunk.decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            data.extend(chunk)
            self.write(decoded)

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
        self.writeln("KAngel commands:")
        self.writeln("  help               Show this command list")
        self.writeln("  info               Show device, build, and shell state")
        self.writeln("  recovery           Show current recovery panic details")
        self.writeln("  apps               List discovered apps")
        self.writeln("  launch <app_id>    Launch an app on the UI thread")
        self.writeln("  logs               List recent log files")
        self.writeln("  logs <name> [n]    Tail a log file")
        self.writeln("  exec <command>     Run one shell command and print output")
        self.writeln("  shell              Enter a raw local shell session")
        self.writeln("  py <code>          Execute Python in-process")
        self.writeln("  pdb                Break into pdb for this session thread")
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

    def _cmd_shell(self, arg_text: str) -> None:
        argv = shlex.split(arg_text) if arg_text.strip() else _default_shell_argv()
        self.writeln(f"entering shell: {' '.join(argv)}")
        self.writeln("type exit to return to KAngel")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(self.manager.base_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
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

        try:
            while not stop.is_set():
                data = self.channel.recv(1024)
                if not data:
                    break
                if proc.stdin is None:
                    break
                proc.stdin.write(data)
                proc.stdin.flush()
        except Exception:
            pass
        finally:
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
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self.writeln("")
            self.writeln("shell closed")

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

    def _cmd_pdb(self) -> None:
        import pdb

        reader = self.channel.makefile("r", -1)
        writer = self.channel.makefile("w", -1)
        namespace = self._build_runtime_namespace()
        manager = self.manager
        host = self.manager.host_window
        recovery_info = self.manager.recovery_info
        debugger = pdb.Pdb(stdin=reader, stdout=writer)
        frame = inspect.currentframe()
        if frame is None:
            self.writeln("pdb unavailable")
            return
        self.writeln("entering pdb on the KAngel session thread")
        debugger.set_trace(frame)
        self._python_locals.update(namespace)

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
        if raw.startswith("exec "):
            self._cmd_exec(raw.partition(" ")[2])
            return True
        if raw.startswith("py "):
            self._cmd_py(raw.partition(" ")[2])
            return True
        if raw == "pdb":
            self._cmd_pdb()
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
        self.writeln("KAngel remote shell")
        self.writeln(f"authenticated as {self.username}")
        self.writeln(f"listening on tcp/{self.manager.port}")
        self.writeln("type 'help' for commands")
        while True:
            line = self._readline("KAngel> ")
            if line is None:
                return
            try:
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

    def _host_key_path(self) -> Path:
        layout = get_user_data_layout(self.base_dir)
        layout.ensure_directories()
        key_dir = layout.data_system / "KAngel"
        key_dir.mkdir(parents=True, exist_ok=True)
        return key_dir / KANGEL_HOST_KEY_NAME

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
            session = KAngelSession(self, channel, server.username)
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
