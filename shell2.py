from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal as dbus_signal

from app_registry import AppDescriptor, discover_apps
from audio import get_audio_info, list_audio_output_devices, set_muted, set_output_device, set_volume
from battery import get_battery_info
from config import ConfigStore, DeviceConfigStore, OSConfig
from fs_layout import get_user_data_layout
from location import get_location_info
from logger import configure as configure_logging
from logger import get_logger
from media import MediaSession
from wifi import (
    add_wifi_profile,
    delete_wifi_profile,
    get_wifi_info,
    list_wifi_profiles,
    scan_wifi_networks,
)


BUS_NAME = "org.deletescapeos.Shell2"
OBJECT_PATH = "/org/deletescapeos/Shell2"
INTERFACE_NAME = "org.deletescapeos.Shell2"

log = get_logger("shell2")


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


def _json(data: Any) -> str:
    return json.dumps(data, default=_json_default, sort_keys=True)


def _descriptor_dict(app: AppDescriptor) -> dict[str, Any]:
    return {
        "app_id": app.app_id,
        "folder": str(app.folder),
        "main_py": str(app.main_py),
        "display_name": app.display_name,
        "bundle_id": app.bundle_id,
        "build": app.build,
        "version": app.version,
        "permissions": list(app.permissions or []),
        "icon_path": str(app.icon_path) if app.icon_path else "",
        "hidden": bool(app.hidden),
        "autostart": bool(app.autostart),
        "receive_custom_qss": bool(app.receive_custom_qss),
    }


class Shell2Service(ServiceInterface):
    def __init__(self, *, base_dir: Path):
        super().__init__(INTERFACE_NAME)
        self.base_dir = base_dir
        self.host_shell = base_dir / "host_shell.py"
        self._config_store = ConfigStore()
        self.config: OSConfig = self._config_store.load()
        self.device = DeviceConfigStore().load()
        self.apps = self._load_apps()
        self._running: dict[str, dict[str, Any]] = {}
        self._media_sessions: dict[str, dict[str, Any]] = {}
        self._background_enabled: dict[str, bool] = {}
        self.active_app_id = ""

    def _load_apps(self) -> dict[str, AppDescriptor]:
        builtin_apps_root = self.base_dir / "apps"
        user_apps_root = get_user_data_layout(self.base_dir).applications
        user_apps = discover_apps(user_apps_root)
        builtins = discover_apps(builtin_apps_root)
        merged = dict(user_apps)
        merged.update(builtins)
        return merged

    def _visible_apps(self) -> list[dict[str, Any]]:
        return [_descriptor_dict(app) for app in self.apps.values() if not app.hidden]

    def _all_apps(self) -> list[dict[str, Any]]:
        return [_descriptor_dict(app) for app in self.apps.values()]

    def _running_apps(self) -> list[dict[str, Any]]:
        self._prune_dead_processes()
        result = []
        for app_id, state in sorted(self._running.items()):
            desc = self.apps.get(app_id)
            item = dict(state)
            item["app_id"] = app_id
            item["display_name"] = desc.display_name if desc else app_id
            item["icon_path"] = str(desc.icon_path) if desc and desc.icon_path else ""
            item["active"] = app_id == self.active_app_id
            item["background_enabled"] = bool(self._background_enabled.get(app_id, False))
            item.pop("process", None)
            result.append(item)
        return result

    def _prune_dead_processes(self) -> None:
        for app_id, state in list(self._running.items()):
            proc = state.get("process")
            if proc is None:
                continue
            if proc.returncode is None:
                continue
            self._mark_app_exited(app_id, int(proc.returncode or 0))

    def _mark_app_exited(self, app_id: str, exit_code: int) -> None:
        state = self._running.pop(app_id, None)
        self._background_enabled.pop(app_id, None)
        if self.active_app_id == app_id:
            self.active_app_id = ""
            self.ActiveAppChanged("")
        if state is not None:
            log.info("Hosted app exited", extra={"app_id": app_id, "exit_code": exit_code})
            self.AppExited(app_id, int(exit_code))
            self.RunningAppsChanged(_json(self._running_apps()))

    async def _watch_process(self, app_id: str, proc: asyncio.subprocess.Process) -> None:
        try:
            exit_code = await proc.wait()
        except Exception:
            log.exception("Failed waiting for hosted app", extra={"app_id": app_id})
            exit_code = -1
        self._mark_app_exited(app_id, int(exit_code))

    async def _launch_app(self, app_id: str, *, show_window: bool = True) -> bool:
        app_id = str(app_id or "").strip()
        if app_id not in self.apps:
            log.warning("Launch requested for unknown app", extra={"app_id": app_id})
            return False

        self._prune_dead_processes()
        existing = self._running.get(app_id)
        if existing is not None:
            self.active_app_id = app_id
            self.ActiveAppChanged(app_id)
            return True

        args = [
            sys.executable,
            str(self.host_shell),
            app_id,
            "--shell-bus-name",
            BUS_NAME,
            "--shell-object-path",
            OBJECT_PATH,
            "--shell-interface",
            INTERFACE_NAME,
        ]
        if not show_window:
            args.append("--hidden")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self.base_dir),
                env=dict(os.environ),
            )
        except Exception:
            log.exception("Failed to spawn host shell", extra={"app_id": app_id})
            return False

        now = time.time()
        self._running[app_id] = {
            "pid": int(proc.pid or 0),
            "started_at": now,
            "started_at_iso": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
            "state": "starting",
            "visible": bool(show_window),
            "process": proc,
        }
        self.active_app_id = app_id if show_window else self.active_app_id
        asyncio.create_task(self._watch_process(app_id, proc))
        log.info("Hosted app spawned", extra={"app_id": app_id, "pid": int(proc.pid or 0), "show_window": bool(show_window)})
        self.AppLaunched(app_id, int(proc.pid or 0))
        self.RunningAppsChanged(_json(self._running_apps()))
        if show_window:
            self.ActiveAppChanged(app_id)
        return True

    @method()
    def Ping(self) -> "s":
        return "ok"

    @method()
    def ReloadApps(self) -> "s":
        self.apps = self._load_apps()
        payload = _json(self._all_apps())
        self.AppsChanged(payload)
        return payload

    @method()
    def GetAllApps(self) -> "s":
        return _json(self._all_apps())

    @method()
    def GetVisibleApps(self) -> "s":
        return _json(self._visible_apps())

    @method()
    def GetRunningApps(self) -> "s":
        return _json(self._running_apps())

    @method()
    async def LaunchApp(self, app_id: "s") -> "b":
        return await self._launch_app(app_id, show_window=True)

    @method()
    async def LaunchAppHidden(self, app_id: "s") -> "b":
        return await self._launch_app(app_id, show_window=False)

    @method()
    def ActivateApp(self, app_id: "s") -> "b":
        app_id = str(app_id or "").strip()
        self._prune_dead_processes()
        if app_id not in self._running:
            return False
        self.active_app_id = app_id
        self.SetWindowState(app_id, "active", True)
        return True

    @method()
    def TerminateApp(self, app_id: "s") -> "b":
        app_id = str(app_id or "").strip()
        state = self._running.get(app_id)
        proc = state.get("process") if state else None
        if proc is None:
            return False
        try:
            proc.terminate()
        except ProcessLookupError:
            self._mark_app_exited(app_id, 0)
        except Exception:
            log.exception("Failed to terminate hosted app", extra={"app_id": app_id})
            return False
        return True

    @method()
    def RegisterHost(self, app_id: "s", pid: "u", visible: "b") -> "b":
        app_id = str(app_id or "").strip()
        if app_id not in self.apps:
            return False
        state = self._running.setdefault(app_id, {})
        state.update({"pid": int(pid), "state": "running", "visible": bool(visible)})
        if visible:
            self.active_app_id = app_id
            self.ActiveAppChanged(app_id)
        self.RunningAppsChanged(_json(self._running_apps()))
        return True

    @method()
    def HostClosed(self, app_id: "s", exit_code: "i") -> "b":
        self._mark_app_exited(str(app_id or "").strip(), int(exit_code))
        return True

    @method()
    def SetWindowState(self, app_id: "s", state: "s", visible: "b") -> "b":
        app_id = str(app_id or "").strip()
        if app_id not in self._running:
            return False
        self._running[app_id]["state"] = str(state or "running")
        self._running[app_id]["visible"] = bool(visible)
        if state == "active":
            self.active_app_id = app_id
            self.ActiveAppChanged(app_id)
        self.WindowStateChanged(app_id, str(state or "running"), bool(visible))
        self.RunningAppsChanged(_json(self._running_apps()))
        return True

    @method()
    def GetConfig(self) -> "s":
        return _json(self.config)

    @method()
    def SetSetting(self, key: "s", value_json: "s") -> "b":
        key = str(key or "")
        if not hasattr(self.config, key):
            return False
        try:
            value = json.loads(value_json)
        except Exception:
            value = value_json
        setattr(self.config, key, value)
        self._config_store.save(self.config)
        self.ConfigChanged(_json(self.config))
        return True

    @method()
    def Notify(self, title: "s", message: "s", duration_ms: "u", app_id: "s") -> "b":
        payload = {
            "title": str(title or ""),
            "message": str(message or ""),
            "duration_ms": int(duration_ms),
            "app_id": str(app_id or ""),
            "created_at": time.time(),
        }
        log.info("Notification requested", extra={"app_id": payload["app_id"], "title": payload["title"]})
        self.NotificationRequested(_json(payload))
        return True

    @method()
    def EnableBackground(self, app_id: "s", enabled: "b") -> "b":
        app_id = str(app_id or "").strip()
        if not app_id:
            return False
        self._background_enabled[app_id] = bool(enabled)
        self.RunningAppsChanged(_json(self._running_apps()))
        return True

    @method()
    def SetMediaSession(self, app_id: "s", payload_json: "s") -> "b":
        app_id = str(app_id or "").strip()
        if not app_id:
            return False
        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = {}
        payload["app_id"] = app_id
        self._media_sessions[app_id] = payload
        self.MediaSessionsChanged(_json(self._media_sessions))
        return True

    @method()
    def ClearMediaSession(self, app_id: "s") -> "b":
        self._media_sessions.pop(str(app_id or "").strip(), None)
        self.MediaSessionsChanged(_json(self._media_sessions))
        return True

    @method()
    def GetActiveMediaSession(self) -> "s":
        for app_id in reversed(list(self._media_sessions.keys())):
            return _json(self._media_sessions[app_id])
        return _json(None)

    @method()
    def SendMediaCommand(self, command: "s", app_id: "s", payload_json: "s") -> "b":
        payload = {}
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
        self.MediaCommandRequested(str(app_id or ""), str(command or ""), _json(payload))
        return True

    @method()
    def GetBatteryInfo(self) -> "s":
        return _json(get_battery_info())

    @method()
    def GetLocationInfo(self) -> "s":
        return _json(get_location_info())

    @method()
    def GetWifiInfo(self) -> "s":
        return _json(get_wifi_info())

    @method()
    def ScanWifiNetworks(self) -> "s":
        return _json(scan_wifi_networks())

    @method()
    def ListWifiProfiles(self) -> "s":
        return _json(list_wifi_profiles())

    @method()
    def AddWifiProfile(self, ssid: "s", password: "s", secure: "b") -> "b":
        return bool(add_wifi_profile(str(ssid or ""), password=str(password or "") or None, secure=bool(secure)))

    @method()
    def DeleteWifiProfile(self, ssid: "s") -> "b":
        return bool(delete_wifi_profile(str(ssid or "")))

    @method()
    def GetAudioInfo(self) -> "s":
        return _json(get_audio_info())

    @method()
    def ListAudioOutputDevices(self) -> "s":
        return _json(list_audio_output_devices())

    @method()
    def SetAudioVolume(self, percent: "u") -> "b":
        return bool(set_volume(int(percent)))

    @method()
    def SetAudioMuted(self, muted: "b") -> "b":
        return bool(set_muted(bool(muted)))

    @method()
    def SetAudioOutputDevice(self, device_id: "s") -> "b":
        return bool(set_output_device(str(device_id or "")))

    @dbus_signal()
    def AppsChanged(self, apps_json: "s") -> "s":
        return apps_json

    @dbus_signal()
    def RunningAppsChanged(self, running_json: "s") -> "s":
        return running_json

    @dbus_signal()
    def ActiveAppChanged(self, app_id: "s") -> "s":
        return app_id

    @dbus_signal()
    def AppLaunched(self, app_id: "s", pid: "u") -> "su":
        return [app_id, pid]

    @dbus_signal()
    def AppExited(self, app_id: "s", exit_code: "i") -> "si":
        return [app_id, exit_code]

    @dbus_signal()
    def WindowStateChanged(self, app_id: "s", state: "s", visible: "b") -> "ssb":
        return [app_id, state, visible]

    @dbus_signal()
    def ConfigChanged(self, config_json: "s") -> "s":
        return config_json

    @dbus_signal()
    def NotificationRequested(self, notification_json: "s") -> "s":
        return notification_json

    @dbus_signal()
    def MediaSessionsChanged(self, sessions_json: "s") -> "s":
        return sessions_json

    @dbus_signal()
    def MediaCommandRequested(self, app_id: "s", command: "s", payload_json: "s") -> "sss":
        return [app_id, command, payload_json]

    async def autostart(self) -> None:
        app_ids = [app.app_id for app in self.apps.values() if app.autostart]
        for app_id in app_ids:
            await self._launch_app(app_id, show_window=False)


async def _amain() -> None:
    parser = argparse.ArgumentParser(description="Headless deletescape shell service")
    parser.add_argument("--no-autostart", action="store_true", help="Do not start apps marked autostart")
    args = parser.parse_args()

    configure_logging()
    base_dir = Path(__file__).resolve().parent
    service = Shell2Service(base_dir=base_dir)
    bus = await MessageBus().connect()
    await bus.request_name(BUS_NAME)
    bus.export(OBJECT_PATH, service)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass

    log.info("shell2 D-Bus service running", extra={"bus_name": BUS_NAME, "object_path": OBJECT_PATH})
    if not args.no_autostart:
        await service.autostart()
    await stop.wait()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
