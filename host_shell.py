from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dbus_next.aio import MessageBus
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QPalette, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget

from app_registry import AppDescriptor, discover_apps, load_app_class
from config import ConfigStore, DeviceConfigStore, OSConfig
from fs_layout import get_user_data_layout
from logger import configure as configure_logging
from logger import get_logger


DEFAULT_BUS_NAME = "org.deletescapeos.Shell2"
DEFAULT_OBJECT_PATH = "/org/deletescapeos/Shell2"
DEFAULT_INTERFACE = "org.deletescapeos.Shell2"

log = get_logger("host_shell")
_ORIGINAL_SUBPROCESS_POPEN = subprocess.Popen


@dataclass
class RemoteAppDescriptor:
    app_id: str
    folder: str = ""
    main_py: str = ""
    display_name: str = ""
    bundle_id: str | None = None
    build: int | None = None
    version: str | None = None
    permissions: list[str] | None = None
    icon_path: str = ""
    hidden: bool = False
    autostart: bool = False
    receive_custom_qss: bool = False


def _camel_to_snake(name: str) -> str:
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", str(name))
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _decode_json(payload: str, default: Any = None) -> Any:
    try:
        return json.loads(payload)
    except Exception:
        return default


def _namespace(data: Any) -> Any:
    if isinstance(data, dict):
        return SimpleNamespace(**{k: _namespace(v) for k, v in data.items()})
    if isinstance(data, list):
        return [_namespace(v) for v in data]
    return data


def _remote_apps(payload: str) -> list[RemoteAppDescriptor]:
    raw = _decode_json(payload, [])
    result: list[RemoteAppDescriptor] = []
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            result.append(
                RemoteAppDescriptor(
                    app_id=str(item.get("app_id") or ""),
                    folder=str(item.get("folder") or ""),
                    main_py=str(item.get("main_py") or ""),
                    display_name=str(item.get("display_name") or item.get("app_id") or ""),
                    bundle_id=item.get("bundle_id"),
                    build=item.get("build"),
                    version=item.get("version"),
                    permissions=list(item.get("permissions") or []),
                    icon_path=str(item.get("icon_path") or ""),
                    hidden=bool(item.get("hidden", False)),
                    autostart=bool(item.get("autostart", False)),
                    receive_custom_qss=bool(item.get("receive_custom_qss", False)),
                )
            )
        except Exception:
            pass
    return result


def _command_metadata(args: Any) -> dict[str, Any]:
    argv: list[str]
    if isinstance(args, (list, tuple)):
        argv = [str(part) for part in args]
    else:
        try:
            argv = shlex.split(str(args or ""))
        except Exception:
            argv = [str(args or "")]
    executable = Path(argv[0]).name if argv else ""
    stems = [executable]
    if executable:
        stems.append(Path(executable).stem)
    return {
        "argv": argv,
        "command": " ".join(argv),
        "executable": executable,
        "match_names": sorted({name.lower() for name in stems if name}),
    }


def _icon_for_descriptor(desc: AppDescriptor | None) -> QIcon | None:
    if desc is None:
        return None

    candidates: list[Path] = []
    if desc.icon_path:
        candidates.append(Path(desc.icon_path))
    if desc.folder:
        candidates.append(Path(desc.folder) / "Assets" / "icon.png")

    for candidate in candidates:
        try:
            if candidate.exists():
                icon = QIcon(str(candidate))
                if not icon.isNull():
                    return icon
        except Exception:
            continue
    return None


def _desktop_file_id(desc: AppDescriptor) -> str:
    raw = desc.bundle_id or f"org.deletescapeos.{desc.app_id}"
    desktop_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw).strip())
    return desktop_id.strip(".-") or str(desc.app_id)


def _desktop_entry_value(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "")


def _ensure_desktop_entry(desc: AppDescriptor, *, host_shell: Path) -> str | None:
    if desc is None or not desc.icon_path:
        return None

    icon_path = Path(desc.icon_path)
    try:
        if not icon_path.exists():
            return None
    except Exception:
        return None

    import random
    import string

    andom_string = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    desktop_id = _desktop_file_id(desc)
    data_home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    applications_dir = data_home / "applications"
    desktop_path = applications_dir / f"{andom_string}{desktop_id}.desktop"
    exec_line = " ".join(
        shlex.quote(part)
        for part in (
            sys.executable,
            str(host_shell),
            desc.app_id,
        )
    )
    content = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={_desktop_entry_value(desc.display_name or desc.app_id)}",
            f"Exec={exec_line}",
            f"Icon={_desktop_entry_value(icon_path)}",
            "Terminal=false",
            "NoDisplay=true",
            f"StartupWMClass={_desktop_entry_value(desktop_id)}",
            "",
        ]
    )

    try:
        applications_dir.mkdir(parents=True, exist_ok=True)
        if not desktop_path.exists() or desktop_path.read_text(encoding="utf-8") != content:
            desktop_path.write_text(content, encoding="utf-8")
    except Exception:
        log.exception("Failed to write hosted app desktop entry", extra={"app_id": desc.app_id})
        return None
    return desktop_id


class ShellDBusClient:
    def __init__(self, *, bus_name: str, object_path: str, interface_name: str):
        self.bus_name = bus_name
        self.object_path = object_path
        self.interface_name = interface_name
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="ShellDBusClient", daemon=True)
        self._bus = None
        self._iface = None
        self._ready = threading.Event()
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.create_task(self._connect())
        self._loop.run_forever()

    async def _connect(self) -> None:
        try:
            self._bus = await MessageBus().connect()
            introspection = await self._bus.introspect(self.bus_name, self.object_path)
            obj = self._bus.get_proxy_object(self.bus_name, self.object_path, introspection)
            self._iface = obj.get_interface(self.interface_name)
        except Exception:
            log.exception("Failed to connect to shell2 D-Bus service")
        finally:
            self._ready.set()

    def available(self) -> bool:
        return self._iface is not None

    async def _call_async(self, method_name: str, *args):
        if self._iface is None:
            raise RuntimeError("shell2 D-Bus service is unavailable")
        method = getattr(self._iface, f"call_{_camel_to_snake(method_name)}")
        return await method(*args)

    def call(self, method_name: str, *args, default: Any = None, timeout: float = 5.0) -> Any:
        if self._iface is None:
            return default
        future = asyncio.run_coroutine_threadsafe(self._call_async(method_name, *args), self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
            log.exception("D-Bus call failed", extra={"method": method_name})
            return default

    def fire_and_forget(self, method_name: str, *args) -> None:
        if self._iface is None:
            return
        asyncio.run_coroutine_threadsafe(self._call_async(method_name, *args), self._loop)

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass


class HostedAppWindow(QMainWindow):
    def __init__(
        self,
        *,
        app_id: str,
        hidden: bool,
        shell_client: ShellDBusClient,
        local_apps: dict[str, AppDescriptor],
    ):
        super().__init__()
        self.app_id = str(app_id or "").strip()
        self.active_app_id = self.app_id
        self._hidden = bool(hidden)
        self._shell = shell_client
        self.apps = local_apps
        self._config_store = ConfigStore()
        self.config: OSConfig = self._load_config()
        self.device = DeviceConfigStore().load()
        self._app_instance = None
        self._closed_notified = False
        self._patch_subprocess_tracking()

        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(self._display_name())
        self.resize(900, 600)

        self._apply_app_icon()

        container = QWidget()
        container.setFocusPolicy(Qt.StrongFocus)
        self.setCentralWidget(container)
        self.container = container

        self._load_app(container)
        self.apply_theme()
        self._register_host()

        if not self._hidden:
            self.show()
            self.raise_()
            self.activateWindow()

    def _display_name(self) -> str:
        desc = self.apps.get(self.app_id)
        if desc is None:
            return self.app_id
        return desc.display_name or self.app_id

    def _app_icon(self) -> QIcon | None:
        return _icon_for_descriptor(self.apps.get(self.app_id))

    def _apply_app_icon(self) -> None:
        icon = self._app_icon()
        if icon is None:
            return
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    def _load_config(self) -> OSConfig:
        remote = self._shell.call("GetConfig", default="")
        data = _decode_json(remote, None) if remote else None
        if isinstance(data, dict):
            config = self._config_store.load()
            for key, value in data.items():
                if hasattr(config, key):
                    try:
                        setattr(config, key, value)
                    except Exception:
                        pass
            return config
        return self._config_store.load()

    def _load_app(self, container: QWidget) -> None:
        desc = self.apps.get(self.app_id)
        if desc is None:
            raise RuntimeError(f"No app with id {self.app_id!r}")
        if desc.app_class is None:
            desc.app_class = load_app_class(desc)
        app_class = desc.app_class
        if app_class is None:
            raise RuntimeError(f"App {self.app_id!r} does not define class App")
        self._app_instance = app_class(window=self, container=container)
        try:
            setattr(self._app_instance, "app_id", self.app_id)
        except Exception:
            pass

    def _register_host(self) -> None:
        self._shell.fire_and_forget("RegisterHost", self.app_id, int(os.getpid()), not self._hidden)

    def _patch_subprocess_tracking(self) -> None:
        owner = self

        class TrackingPopen(_ORIGINAL_SUBPROCESS_POPEN):
            def __init__(self, *popen_args, **popen_kwargs):
                super().__init__(*popen_args, **popen_kwargs)
                try:
                    command_args = popen_kwargs.get("args", popen_args[0] if popen_args else None)
                    owner._report_launched_process(int(self.pid or 0), command_args)
                except Exception:
                    log.exception("Failed to report launched process", extra={"app_id": owner.app_id})

        subprocess.Popen = TrackingPopen

    def _report_launched_process(self, pid: int, args: Any) -> None:
        if pid <= 0:
            return
        payload = _command_metadata(args)
        self._shell.fire_and_forget("RegisterLaunchedProcess", self.app_id, int(pid), json.dumps(payload))

    def _notify_closed(self, exit_code: int = 0) -> None:
        if self._closed_notified:
            return
        self._closed_notified = True
        self._shell.fire_and_forget("HostClosed", self.app_id, int(exit_code))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._shell.fire_and_forget("SetWindowState", self.app_id, "active", self.isVisible())

    def closeEvent(self, event) -> None:
        try:
            hook = getattr(self._app_instance, "on_quit", None)
            if callable(hook):
                hook()
        except Exception:
            log.exception("App on_quit hook failed", extra={"app_id": self.app_id})
        self._notify_closed(0)
        super().closeEvent(event)

    def format_time(self, dt: datetime) -> str:
        if getattr(self.config, "use_24h_time", True):
            return dt.strftime("%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")

    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        try:
            app.setStyle("FluentWinUi3")
        except Exception:
            pass
        # Color scheme
        if not os.name == "nt":
            if self.config.dark_mode:
                app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

                # Custom dark palette
                palette = QPalette()
                palette.setColor(QPalette.Window, QColor("#131313"))
                palette.setColor(QPalette.WindowText, Qt.white)
                palette.setColor(QPalette.Base, QColor(35, 35, 35))
                palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
                palette.setColor(QPalette.ToolTipBase, Qt.white)
                palette.setColor(QPalette.ToolTipText, Qt.white)
                palette.setColor(QPalette.Text, Qt.white)
                palette.setColor(QPalette.Button, QColor(53, 53, 53))
                palette.setColor(QPalette.ButtonText, Qt.white)
                palette.setColor(QPalette.BrightText, Qt.red)
                palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
                palette.setColor(QPalette.HighlightedText, Qt.black)

                app.setPalette(palette)

            else:
                palette = QPalette()
                app.styleHints().setColorScheme(Qt.ColorScheme.Light)
                palette.setColor(QPalette.Window, QColor("#F0F0F0"))
                palette.setColor(QPalette.WindowText, Qt.black)
                palette.setColor(QPalette.Base, Qt.white)
                palette.setColor(QPalette.AlternateBase, QColor("#E0E0E0"))
                palette.setColor(QPalette.ToolTipBase, Qt.black)
                palette.setColor(QPalette.ToolTipText, Qt.white)
                palette.setColor(QPalette.Text, Qt.black)
                palette.setColor(QPalette.Button, QColor("#E0E0E0"))
                palette.setColor(QPalette.ButtonText, Qt.black)
                palette.setColor(QPalette.BrightText, Qt.red)
                palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
                palette.setColor(QPalette.HighlightedText, Qt.white)
                app.setPalette(palette)
        else:
            if self.config.dark_mode:
                app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
            else:
                app.styleHints().setColorScheme(Qt.ColorScheme.Light)
                
    def launch_app(self, app_id: str) -> bool:
        return bool(self._shell.call("LaunchApp", str(app_id or ""), default=False))

    def launch_all_apps(self) -> None:
        for app in self.get_visible_apps():
            self.launch_app(app.app_id)

    def get_visible_apps(self) -> list[RemoteAppDescriptor]:
        remote = self._shell.call("GetVisibleApps", default="")
        if remote:
            return _remote_apps(remote)
        return [
            RemoteAppDescriptor(
                app_id=app.app_id,
                folder=str(app.folder),
                main_py=str(app.main_py),
                display_name=app.display_name,
                bundle_id=app.bundle_id,
                build=app.build,
                version=app.version,
                permissions=list(app.permissions or []),
                icon_path=str(app.icon_path) if app.icon_path else "",
                hidden=app.hidden,
                autostart=app.autostart,
                receive_custom_qss=app.receive_custom_qss,
            )
            for app in self.apps.values()
            if not app.hidden
        ]

    def get_all_apps(self) -> list[RemoteAppDescriptor]:
        remote = self._shell.call("GetAllApps", default="")
        if remote:
            return _remote_apps(remote)
        return [
            RemoteAppDescriptor(
                app_id=app.app_id,
                folder=str(app.folder),
                main_py=str(app.main_py),
                display_name=app.display_name,
                bundle_id=app.bundle_id,
                build=app.build,
                version=app.version,
                permissions=list(app.permissions or []),
                icon_path=str(app.icon_path) if app.icon_path else "",
                hidden=app.hidden,
                autostart=app.autostart,
                receive_custom_qss=app.receive_custom_qss,
            )
            for app in self.apps.values()
        ]

    def get_running_apps(self) -> list[Any]:
        remote = self._shell.call("GetRunningApps", default="[]")
        return _namespace(_decode_json(remote, []))

    def set_setting(self, key: str, value: Any) -> bool:
        ok = bool(self._shell.call("SetSetting", str(key or ""), json.dumps(value), default=False))
        if ok and hasattr(self.config, key):
            try:
                setattr(self.config, key, value)
            except Exception:
                pass
            if key == "dark_mode":
                self.apply_theme()
        return ok

    def notify(self, *, title: str, message: str = "", duration_ms: int = 3500, app_id: str | None = None) -> bool:
        return bool(
            self._shell.call(
                "Notify",
                str(title or ""),
                str(message or ""),
                int(duration_ms),
                str(app_id or self.app_id or ""),
                default=False,
            )
        )

    def enable_background(self, enabled: bool = True, *, app_id: str | None = None) -> bool:
        return bool(self._shell.call("EnableBackground", str(app_id or self.app_id or ""), bool(enabled), default=False))

    def register_background_task(
        self,
        callback,
        *,
        interval_ms: int = 1000,
        name: str = "background_task",
        app_id: str | None = None,
        start_immediately: bool = False,
    ):
        owner = str(app_id or self.app_id or "")
        self.enable_background(True, app_id=owner)
        timer = QTimer(self)
        timer.setInterval(int(interval_ms))
        timer.timeout.connect(callback)
        if start_immediately:
            QTimer.singleShot(0, callback)
        timer.start()
        return SimpleNamespace(task_id=f"{owner}:{name}:{id(timer)}", cancel=timer.stop, timer=timer)

    def background_tasks_allowed(self) -> bool:
        return True

    def has_unlocked_once(self) -> bool:
        return True

    def set_media_session(
        self,
        *,
        title: str = "",
        artist: str = "",
        album: str = "",
        artwork_path: str = "",
        position_ms: int | None = None,
        duration_ms: int | None = None,
        playback_state: str = "playing",
        controls: dict[str, Any] | None = None,
        app_id: str | None = None,
    ) -> bool:
        payload = {
            "title": title,
            "artist": artist,
            "album": album,
            "artwork_path": artwork_path,
            "position_ms": position_ms,
            "duration_ms": duration_ms,
            "playback_state": playback_state,
            "available_commands": sorted((controls or {}).keys()),
            "updated_at": time.time(),
        }
        return bool(self._shell.call("SetMediaSession", str(app_id or self.app_id or ""), json.dumps(payload), default=False))

    update_media_session = set_media_session

    def clear_media_session(self, *, app_id: str | None = None) -> bool:
        return bool(self._shell.call("ClearMediaSession", str(app_id or self.app_id or ""), default=False))

    def get_active_media_session(self) -> Any | None:
        payload = self._shell.call("GetActiveMediaSession", default="null")
        return _namespace(_decode_json(payload, None))

    def send_media_command(self, command: str, *, app_id: str | None = None, **payload) -> bool:
        return bool(
            self._shell.call(
                "SendMediaCommand",
                str(command or ""),
                str(app_id or ""),
                json.dumps(payload or {}),
                default=False,
            )
        )

    def get_battery_info(self) -> Any:
        return _namespace(_decode_json(self._shell.call("GetBatteryInfo", default="{}"), {}))

    def get_location_info(self) -> Any:
        return _namespace(_decode_json(self._shell.call("GetLocationInfo", default="{}"), {}))

    def get_wifi_info(self) -> Any:
        return _namespace(_decode_json(self._shell.call("GetWifiInfo", default="{}"), {}))

    def scan_wifi_networks(self) -> list[Any]:
        return _namespace(_decode_json(self._shell.call("ScanWifiNetworks", default="[]"), []))

    def list_wifi_profiles(self) -> list[Any]:
        return _namespace(_decode_json(self._shell.call("ListWifiProfiles", default="[]"), []))

    def add_wifi_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        return bool(self._shell.call("AddWifiProfile", str(ssid or ""), str(password or ""), bool(secure), default=False))

    def delete_wifi_profile(self, ssid: str) -> bool:
        return bool(self._shell.call("DeleteWifiProfile", str(ssid or ""), default=False))

    def get_audio_info(self) -> Any:
        return _namespace(_decode_json(self._shell.call("GetAudioInfo", default="{}"), {}))

    def list_audio_output_devices(self) -> list[Any]:
        return _namespace(_decode_json(self._shell.call("ListAudioOutputDevices", default="[]"), []))

    def set_audio_volume(self, percent: int) -> bool:
        return bool(self._shell.call("SetAudioVolume", int(percent), default=False))

    def set_audio_muted(self, muted: bool) -> bool:
        return bool(self._shell.call("SetAudioMuted", bool(muted), default=False))

    def set_audio_output_device(self, device_id: str) -> bool:
        return bool(self._shell.call("SetAudioOutputDevice", str(device_id or ""), default=False))


def _load_apps(base_dir: Path) -> dict[str, AppDescriptor]:
    builtin_apps_root = base_dir / "apps"
    user_apps_root = get_user_data_layout(base_dir).applications
    user_apps = discover_apps(user_apps_root)
    builtins = discover_apps(builtin_apps_root)
    merged = dict(user_apps)
    merged.update(builtins)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Host one deletescape app in its own process")
    parser.add_argument("app_id", help="Application id to host")
    parser.add_argument("--hidden", action="store_true", help="Instantiate the app without showing a window")
    parser.add_argument("--shell-bus-name", default=DEFAULT_BUS_NAME)
    parser.add_argument("--shell-object-path", default=DEFAULT_OBJECT_PATH)
    parser.add_argument("--shell-interface", default=DEFAULT_INTERFACE)
    args = parser.parse_args()

    configure_logging()
    base_dir = Path(__file__).resolve().parent
    apps = _load_apps(base_dir)

    desc = apps.get(args.app_id)
    if desc is not None:
        desktop_id = _ensure_desktop_entry(desc, host_shell=base_dir / "host_shell.py")
        # Set this before QApplication is constructed so Wayland/X11 identify
        # the hosted window as the app instead of as the Python interpreter.
        QApplication.setDesktopFileName(desktop_id or desc.app_id)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(not bool(args.hidden))
    if desc is not None:
        app.setApplicationName(desc.display_name or desc.app_id)
        app.setApplicationDisplayName(desc.display_name or desc.app_id)

    shell_client = ShellDBusClient(
        bus_name=args.shell_bus_name,
        object_path=args.shell_object_path,
        interface_name=args.shell_interface,
    )

    if args.app_id not in apps:
        QMessageBox.critical(None, "Unknown App", f"No app with id '{args.app_id}'")
        sys.exit(2)

    icon = _icon_for_descriptor(desc)
    if icon is not None:
        app.setWindowIcon(icon)

    try:
        window = HostedAppWindow(
            app_id=args.app_id,
            hidden=bool(args.hidden),
            shell_client=shell_client,
            local_apps=apps,
        )
    except Exception as exc:
        log.exception("Failed to host app", extra={"app_id": str(args.app_id)})
        QMessageBox.critical(None, "App Launch Failed", f"Failed to launch '{args.app_id}':\n\n{exc}")
        shell_client.fire_and_forget("HostClosed", str(args.app_id), 1)
        sys.exit(1)

    exit_code = app.exec()
    try:
        window._notify_closed(int(exit_code))
    except Exception:
        pass
    shell_client.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
