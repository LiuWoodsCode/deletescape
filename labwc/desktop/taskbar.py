from __future__ import annotations

import asyncio
import json
import os
import re
import select
import sys
import threading
import tempfile
import textwrap
from pathlib import Path
from importlib import import_module
from queue import SimpleQueue
from dataclasses import dataclass, field
from typing import Any

from dbus_next.aio import MessageBus
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell, Pango


SHELL_BUS_NAME = "org.deletescapeos.Shell2"
SHELL_OBJECT_PATH = "/org/deletescapeos/Shell2"
SHELL_INTERFACE = "org.deletescapeos.Shell2"
WLR_PROTOCOL_XML = """
<protocol name="wlr_foreign_toplevel_management_unstable_v1">
  <interface name="zwlr_foreign_toplevel_manager_v1" version="3">
    <request name="stop" type="destructor"/>
    <event name="toplevel">
      <arg name="toplevel" type="new_id" interface="zwlr_foreign_toplevel_handle_v1"/>
    </event>
    <event name="finished"/>
  </interface>
  <interface name="zwlr_foreign_toplevel_handle_v1" version="3">
    <enum name="state">
      <entry name="maximized" value="0"/>
      <entry name="minimized" value="1"/>
      <entry name="activated" value="2"/>
      <entry name="fullscreen" value="3"/>
    </enum>
    <request name="set_maximized"/>
    <request name="unset_maximized"/>
    <request name="set_minimized"/>
    <request name="unset_minimized"/>
    <request name="activate">
      <arg name="seat" type="object" interface="wl_seat"/>
    </request>
    <request name="close"/>
    <request name="set_rectangle">
      <arg name="surface" type="object" interface="wl_surface" allow-null="true"/>
      <arg name="x" type="int"/>
      <arg name="y" type="int"/>
      <arg name="width" type="int"/>
      <arg name="height" type="int"/>
    </request>
    <request name="destroy" type="destructor"/>
    <event name="title">
      <arg name="title" type="string"/>
    </event>
    <event name="app_id">
      <arg name="app_id" type="string"/>
    </event>
    <event name="output_enter">
      <arg name="output" type="object" interface="wl_output"/>
    </event>
    <event name="output_leave">
      <arg name="output" type="object" interface="wl_output"/>
    </event>
    <event name="state">
      <arg name="state" type="array"/>
    </event>
    <event name="done"/>
    <event name="closed"/>
    <event name="parent">
      <arg name="parent" type="object" interface="zwlr_foreign_toplevel_handle_v1" allow-null="true"/>
    </event>
  </interface>
</protocol>
"""


def _camel_to_snake(name: str) -> str:
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", str(name))
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _decode_json(payload: Any, default: Any) -> Any:
    if not isinstance(payload, str) or not payload:
        return default
    try:
        return json.loads(payload)
    except Exception:
        return default


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("utf-8", errors="replace")
    return str(value or "")


@dataclass
class AppInfo:
    app_id: str
    display_name: str = ""
    icon_path: str = ""


@dataclass
class RunningAppInfo:
    app_id: str
    pid: int = 0
    child_pids: tuple[int, ...] = ()
    launched_processes: tuple[dict[str, Any], ...] = ()
    display_name: str = ""
    icon_path: str = ""


@dataclass
class WindowInfo:
    key: str
    title: str
    app_id: str = ""
    pid: int = 0
    window_id: str = ""
    active: bool = False
    visible: bool = True
    source: str = "shell2"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def group_key(self) -> str:
        if self.app_id:
            return self.app_id
        if self.pid:
            return f"pid:{self.pid}"
        return self.key


class Shell2Client:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="TaskbarShell2Client", daemon=True)
        self._bus = None
        self._iface = None
        self._ready = threading.Event()
        self._thread.start()
        self._ready.wait(timeout=4.0)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.create_task(self._connect())
        self._loop.run_forever()

    async def _connect(self) -> None:
        try:
            self._bus = await MessageBus().connect()
            introspection = await self._bus.introspect(SHELL_BUS_NAME, SHELL_OBJECT_PATH)
            obj = self._bus.get_proxy_object(SHELL_BUS_NAME, SHELL_OBJECT_PATH, introspection)
            self._iface = obj.get_interface(SHELL_INTERFACE)
        except Exception as exc:
            print(f"taskbar: failed to connect to Shell2 over D-Bus: {exc}", file=sys.stderr)
        finally:
            self._ready.set()

    async def _call_async(self, method_name: str, *args):
        if self._iface is None:
            raise RuntimeError("Shell2 D-Bus service is unavailable")
        method = getattr(self._iface, f"call_{_camel_to_snake(method_name)}")
        return await method(*args)

    def call(self, method_name: str, *args, default: Any = None, timeout: float = 4.0) -> Any:
        if self._iface is None:
            return default
        future = asyncio.run_coroutine_threadsafe(self._call_async(method_name, *args), self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
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


class WaylandWindowCollector:
    def __init__(self):
        self._available = False
        self._windows: list[WindowInfo] = []
        self._handles: dict[str, Any] = {}
        self._managers: list[Any] = []
        self._globals: dict[str, tuple[int, int]] = {}
        self._seat = None
        self._commands: SimpleQueue[tuple[str, str]] = SimpleQueue()
        self._status = "starting"
        self._thread = threading.Thread(target=self._run, name="TaskbarWaylandWindows", daemon=True)
        self._thread.start()

    def windows(self) -> list[WindowInfo]:
        return list(self._windows)

    def manage_window(self, window_id: str, action: str) -> bool:
        window_id = str(window_id or "")
        action = str(action or "")
        if not window_id or not action:
            return False
        if window_id not in self._handles:
            return False
        if action == "activate" and self._seat is None:
            return False
        self._commands.put((window_id, action))
        return True

    def can_manage_window(self, window_id: str, action: str = "") -> bool:
        window_id = str(window_id or "")
        if not window_id or window_id not in self._handles:
            return False
        return not (action == "activate" and self._seat is None)

    def status(self) -> str:
        return self._status

    def _run(self) -> None:
        try:
            from pywayland.client import Display
            from pywayland.protocol.wayland import WlSeat
        except Exception:
            return

        try:
            display = Display()
            display.connect()
            self._status = "connected"
            registry = display.get_registry()
            registry.dispatcher["global"] = self._on_registry_global
            registry.dispatcher["global_remove"] = self._on_registry_global_remove
            display.roundtrip()

            seat_item = self._globals.get("wl_seat")
            if seat_item is not None:
                name, version = seat_item
                self._seat = registry.bind(name, WlSeat, min(version, 9))

            if not self._bind_supported_toplevel_protocol(display, registry):
                self._status = "no supported toplevel protocol"
                display.disconnect()
                return

            display.roundtrip()
            display.dispatch(block=False)
            self._available = True
            self._status = "ready"
            while True:
                self._drain_commands()
                display.flush()
                readable, _, _ = select.select([display.get_fd()], [], [], 0.1)
                if readable:
                    display.dispatch(block=True)
                else:
                    display.dispatch(block=False)
        except Exception as exc:
            self._status = f"error: {exc}"
            print(f"taskbar: pywayland window collection unavailable: {exc}", file=sys.stderr)

    def _on_registry_global(self, _registry, name: int, interface: str, version: int) -> None:
        self._globals[_text(interface)] = (int(name), int(version))

    def _on_registry_global_remove(self, _registry, name: int) -> None:
        for interface, (global_name, _version) in list(self._globals.items()):
            if global_name == int(name):
                self._globals.pop(interface, None)

    def _bind_supported_toplevel_protocol(self, _display, registry) -> bool:
        # pywayland can only bind extension protocols when their generated
        # modules are installed. labwc commonly exposes wlr-foreign-toplevel;
        # some stacks expose KDE's plasma window management, which includes PID.
        return (
            self._bind_plasma_window_management(registry)
            or self._bind_wlr_foreign_toplevel(registry)
        )

    def _bind_plasma_window_management(self, registry) -> bool:
        item = self._globals.get("org_kde_plasma_window_management")
        if item is None:
            return False
        OrgKdePlasmaWindowManagement = self._import_protocol_class(
            (
                "pywayland.protocol.plasma_window_management",
                "pywayland.protocol.plasma_window_management_unstable_v1",
                "pywayland.protocol.org_kde_plasma_window_management",
            ),
            "OrgKdePlasmaWindowManagement",
        )
        if OrgKdePlasmaWindowManagement is None:
            return False

        name, version = item
        manager = registry.bind(name, OrgKdePlasmaWindowManagement, min(version, 16))
        manager.dispatcher["show_desktop_changed"] = lambda *_args: None
        manager.dispatcher["window"] = self._on_plasma_window
        self._managers.append(manager)
        return True

    def _on_plasma_window(self, _manager, handle) -> None:
        data: dict[str, Any] = {"source": "pywayland-plasma"}

        def update(**values) -> None:
            data.update(values)
            self._upsert_window(data)

        handle.dispatcher["title_changed"] = lambda _h, title: update(title=_text(title) or "Window")
        handle.dispatcher["app_id_changed"] = lambda _h, app_id: update(app_id=_text(app_id))
        handle.dispatcher["pid_changed"] = lambda _h, pid: update(pid=int(pid or 0))
        handle.dispatcher["active_changed"] = lambda _h, active: update(active=bool(active))
        handle.dispatcher["minimized_changed"] = lambda _h, minimized: update(visible=not bool(minimized))
        handle.dispatcher["unmapped"] = lambda _h: self._remove_window(str(id(handle)))
        data["window_id"] = str(id(handle))
        self._upsert_window(data)

    def _bind_wlr_foreign_toplevel(self, registry) -> bool:
        item = self._globals.get("zwlr_foreign_toplevel_manager_v1")
        if item is None:
            return False
        ZwlrForeignToplevelManagerV1 = self._import_protocol_class(
            (
                "pywayland.protocol.wlr_foreign_toplevel_management_unstable_v1",
                "pywayland.protocol.wlr_foreign_toplevel_management_unstable_v1.zwlr_foreign_toplevel_manager_v1",
                "ds_wayland_protocols.wlr_foreign_toplevel_management_unstable_v1",
                "pywayland.protocol.ext_foreign_toplevel_list_v1",
            ),
            "ZwlrForeignToplevelManagerV1",
        )
        if ZwlrForeignToplevelManagerV1 is None:
            ZwlrForeignToplevelManagerV1 = self._generate_wlr_protocol_class()
        if ZwlrForeignToplevelManagerV1 is None:
            return False

        name, version = item
        manager = registry.bind(name, ZwlrForeignToplevelManagerV1, min(version, 3))
        manager.dispatcher["toplevel"] = self._on_wlr_toplevel
        manager.dispatcher["finished"] = lambda *_args: None
        self._managers.append(manager)
        self._status = "bound wlr foreign toplevel"
        return True

    def _import_protocol_class(self, module_names: tuple[str, ...], class_name: str):
        for module_name in module_names:
            try:
                module = import_module(module_name)
                value = getattr(module, class_name, None)
                if value is not None:
                    return value
            except Exception:
                continue
        return None

    def _on_wlr_toplevel(self, _manager, handle) -> None:
        data: dict[str, Any] = {
            "source": "pywayland-wlr-foreign-toplevel",
            "window_id": str(id(handle)),
        }

        def update(**values) -> None:
            data.update(values)
            self._upsert_window(data)

        handle.dispatcher["title"] = lambda _h, title: update(title=_text(title) or "Window")
        handle.dispatcher["app_id"] = lambda _h, app_id: update(app_id=_text(app_id))
        handle.dispatcher["state"] = lambda _h, state: update(active=self._wlr_state_is_active(state))
        handle.dispatcher["closed"] = lambda _h: self._remove_window(str(id(handle)))
        handle.dispatcher["done"] = lambda _h: self._upsert_window(data)
        self._handles[data["window_id"]] = handle
        self._upsert_window(data)

    def _wlr_state_is_active(self, state) -> bool:
        try:
            values = bytes(state)
        except Exception:
            values = state if isinstance(state, (list, tuple)) else []
        # zwlr_foreign_toplevel_handle_v1.state.activated is value 2.
        return 2 in values

    def _upsert_window(self, data: dict[str, Any]) -> None:
        window = self._window_from_data(data)
        windows = [item for item in self._windows if item.key != window.key]
        windows.append(window)
        self._windows = windows

    def _remove_window(self, key: str) -> None:
        self._handles.pop(str(key), None)
        self._windows = [item for item in self._windows if item.key != key]

    def _drain_commands(self) -> None:
        while not self._commands.empty():
            window_id, action = self._commands.get()
            handle = self._handles.get(window_id)
            if handle is None:
                continue
            self._run_command(handle, action)

    def _run_command(self, handle, action: str) -> None:
        try:
            if action == "activate" and self._seat is not None:
                handle.activate(self._seat)
            elif action == "minimize":
                handle.set_minimized()
            elif action == "restore":
                handle.unset_minimized()
            elif action == "maximize":
                handle.set_maximized()
            elif action == "unmaximize":
                handle.unset_maximized()
            elif action == "close":
                handle.close()
            self._status = f"{action} requested"
        except Exception as exc:
            self._status = f"{action} failed: {exc}"
            print(f"taskbar: failed to {action} Wayland window: {exc}", file=sys.stderr)

    def _generate_wlr_protocol_class(self):
        try:
            from pywayland.scanner.protocol import Protocol
        except Exception:
            return None

        root = Path(tempfile.gettempdir()) / "deletescape_pywayland_protocols"
        package = root / "ds_wayland_protocols"
        xml_path = root / "wlr-foreign-toplevel-management-unstable-v1.xml"
        try:
            package.mkdir(parents=True, exist_ok=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            wayland = package / "wayland"
            wayland.mkdir(exist_ok=True)
            (wayland / "__init__.py").write_text(
                "from pywayland.protocol.wayland import WlOutput, WlSeat, WlSurface\n",
                encoding="utf-8",
            )
            xml_path.write_text(textwrap.dedent(WLR_PROTOCOL_XML).strip(), encoding="utf-8")
            protocol = Protocol.parse_file(str(xml_path))
            protocol.output(
                str(package),
                {
                    "zwlr_foreign_toplevel_manager_v1": "wlr_foreign_toplevel_management_unstable_v1",
                    "zwlr_foreign_toplevel_handle_v1": "wlr_foreign_toplevel_management_unstable_v1",
                    "wl_output": "wayland",
                    "wl_seat": "wayland",
                    "wl_surface": "wayland",
                },
            )
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            module = import_module("ds_wayland_protocols.wlr_foreign_toplevel_management_unstable_v1")
            return getattr(module, "ZwlrForeignToplevelManagerV1", None)
        except Exception as exc:
            print(f"taskbar: failed to generate wlr toplevel protocol: {exc}", file=sys.stderr)
            return None

    def _window_from_data(self, data: dict[str, Any]) -> WindowInfo:
        window_id = str(data.get("window_id") or "")
        app_id = str(data.get("app_id") or "")
        pid = int(data.get("pid") or 0)
        title = str(data.get("title") or app_id or "Window")
        key = window_id or f"{app_id}:{pid}:{title}"
        return WindowInfo(
            key=key,
            title=title,
            app_id=app_id,
            pid=pid,
            window_id=window_id,
            active=bool(data.get("active", False)),
            visible=bool(data.get("visible", True)),
            source=str(data.get("source") or "pywayland"),
            raw=dict(data),
        )


class Taskbar(Gtk.Window):
    HEIGHT = 40
    ICON_SIZE = 18

    def __init__(self):
        super().__init__(title="Taskbar")
        self._shell = Shell2Client()
        self._wayland = WaylandWindowCollector()
        self._apps: dict[str, AppInfo] = {}
        self._running_apps: dict[str, RunningAppInfo] = {}
        self._groups: dict[str, list[WindowInfo]] = {}
        self._buttons: dict[str, Gtk.Button] = {}
        self._desktop_icon_cache: dict[tuple[str, str], tuple[str, str]] = {}

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(1, self.HEIGHT)
        self.connect("destroy", self._on_destroy)

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 0)
        GtkLayerShell.set_exclusive_zone(self, self.HEIGHT)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_namespace(self, "deletescape-taskbar")

        self._install_css()
        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._box.set_margin_start(4)
        self._box.set_margin_end(4)
        self._box.set_margin_top(4)
        self._box.set_margin_bottom(4)
        self.add(self._box)

        self.refresh()
        GLib.timeout_add(100, self._refresh_tick)

    def _install_css(self) -> None:
        css = b"""
        window {
            background: #202020;
            color: white;
            font-size: 12px;
        }
        button.taskbar-button {
            background: #303030;
            border: 1px solid #505050;
            border-radius: 0;
            color: white;
            min-height: 28px;
            min-width: 92px;
            padding: 4px 10px;
        }
        button.taskbar-button:hover {
            background: #404040;
        }
        button.taskbar-button.active {
            background: #34445a;
            border-color: #7fb5ff;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _on_destroy(self, *_args) -> None:
        self._shell.close()
        Gtk.main_quit()

    def _refresh_tick(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        self._apps = self._fetch_apps()
        self._running_apps = self._fetch_running_apps()
        windows = self._fetch_windows()
        windows.extend(self._wayland.windows())
        windows = self._dedupe_windows(windows)
        windows = self._attach_launched_windows(windows)
        windows = self._merge_running_app_placeholders(windows)
        if not windows:
            windows = self._windows_from_running_apps(self._running_apps.values())
        self._set_groups(self._group_windows(windows))

    def _fetch_apps(self) -> dict[str, AppInfo]:
        payload = self._shell.call("GetAllApps", default="[]")
        apps: dict[str, AppInfo] = {}
        for item in _decode_json(payload, []):
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("app_id") or "").strip()
            if not app_id:
                continue
            apps[app_id] = AppInfo(
                app_id=app_id,
                display_name=str(item.get("display_name") or app_id),
                icon_path=str(item.get("icon_path") or ""),
            )
        return apps

    def _fetch_running_apps(self) -> dict[str, RunningAppInfo]:
        payload = self._shell.call("GetRunningApps", default="[]")
        raw_apps = _decode_json(payload, [])
        if not isinstance(raw_apps, list):
            return {}
        apps: dict[str, RunningAppInfo] = {}
        for item in raw_apps:
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("app_id") or "").strip()
            if not app_id:
                continue
            apps[app_id] = RunningAppInfo(
                app_id=app_id,
                pid=int(item.get("pid") or 0),
                child_pids=self._pid_tuple(item.get("child_pids", [])),
                launched_processes=tuple(proc for proc in item.get("launched_processes", []) if isinstance(proc, dict)),
                display_name=str(item.get("display_name") or app_id),
                icon_path=str(item.get("icon_path") or ""),
            )
        return apps

    def _pid_tuple(self, values) -> tuple[int, ...]:
        pids = []
        if not isinstance(values, list):
            return ()
        for value in values:
            try:
                pid = int(value)
            except Exception:
                continue
            if pid > 0:
                pids.append(pid)
        return tuple(pids)

    def _fetch_windows(self) -> list[WindowInfo]:
        # Shell2 can back this with labwc/wlr-foreign-toplevel data.
        payload = self._shell.call("GetWindows", default="")
        raw_windows = _decode_json(payload, [])
        if not isinstance(raw_windows, list):
            return []
        windows = []
        for item in raw_windows:
            if isinstance(item, dict):
                windows.append(self._window_from_payload(item))
        return windows

    def _windows_from_running_apps(self, running_apps) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        for app in running_apps:
            app_id = str(app.app_id or "").strip()
            if not app_id:
                continue
            windows.append(
                WindowInfo(
                    key=f"app:{app_id}",
                    title=str(app.display_name or app_id),
                    app_id=app_id,
                    pid=int(app.pid or 0),
                    source="running-app",
                )
            )
        return windows

    def _window_from_payload(self, item: dict[str, Any]) -> WindowInfo:
        app_id = str(item.get("app_id") or item.get("appId") or item.get("app-id") or "").strip()
        title = str(item.get("title") or item.get("name") or item.get("display_name") or app_id or "Window")
        window_id = str(item.get("window_id") or item.get("id") or item.get("handle") or "").strip()
        pid = int(item.get("pid") or item.get("process_id") or 0)
        key = window_id or f"{app_id}:{pid}:{title}"
        return WindowInfo(
            key=key,
            title=title,
            app_id=app_id,
            pid=pid,
            window_id=window_id,
            active=bool(item.get("active", item.get("focused", False))),
            visible=bool(item.get("visible", True)),
            source=str(item.get("source") or "window"),
            raw=item,
        )

    def _dedupe_windows(self, windows: list[WindowInfo]) -> list[WindowInfo]:
        merged: dict[str, WindowInfo] = {}
        for window in windows:
            key = window.window_id or (f"pid:{window.pid}" if window.pid else window.key)
            existing = merged.get(key)
            if existing is None:
                merged[key] = window
                continue
            if not existing.pid and window.pid:
                existing.pid = window.pid
            if not existing.app_id and window.app_id:
                existing.app_id = window.app_id
            if existing.title == "Window" and window.title:
                existing.title = window.title
            existing.active = existing.active or window.active
            existing.visible = existing.visible and window.visible
            existing.raw.update(window.raw)
        return list(merged.values())

    def _merge_running_app_placeholders(self, windows: list[WindowInfo]) -> list[WindowInfo]:
        represented_app_ids = {window.app_id for window in windows if window.app_id}
        represented_pids = {window.pid for window in windows if window.pid > 0}
        result = list(windows)

        for app in self._running_apps.values():
            if not app.app_id:
                continue
            if app.app_id in represented_app_ids:
                continue
            app_pids = {app.pid, *app.child_pids}
            app_pids.discard(0)
            if app_pids and represented_pids.intersection(app_pids):
                continue
            # result.extend(self._windows_from_running_apps([app]))
        return result

    def _attach_launched_windows(self, windows: list[WindowInfo]) -> list[WindowInfo]:
        app_descendants = self._app_descendant_pids()

        attached = []
        for window in windows:
            app_id = (
                self._owning_app_id(window.pid, app_descendants)
                or self._owning_app_id_by_window_identity(window)
                or self._owning_app_id_by_app_metadata(window)
            )
            if app_id:
                window.raw.setdefault("reported_app_id", window.app_id)
                window.raw["launched_by_app_id"] = app_id
                window.app_id = app_id
            attached.append(window)
        return attached

    def _owning_app_id_by_window_identity(self, window: WindowInfo) -> str:
        identity = self._normalized_window_identity(window)
        if not identity:
            return ""
        for app_id, app in self._running_apps.items():
            for proc in app.launched_processes:
                match_names = proc.get("match_names", [])
                if not isinstance(match_names, list):
                    continue
                for name in match_names:
                    if self._normalize_name(name) and self._normalize_name(name) in identity:
                        return app_id
        return ""

    def _owning_app_id_by_app_metadata(self, window: WindowInfo) -> str:
        identity = self._normalized_window_identity(window)
        if not identity:
            return ""
        for app_id, app in self._running_apps.items():
            candidates = {
                self._normalize_name(app_id),
                self._normalize_name(app.display_name),
            }
            candidates.discard("")
            if identity.intersection(candidates):
                return app_id
        return ""

    def _normalized_window_identity(self, window: WindowInfo) -> set[str]:
        values = {
            window.app_id,
            window.title,
            window.raw.get("reported_app_id", ""),
            window.raw.get("app_id", ""),
            window.raw.get("appId", ""),
        }
        result = set()
        for value in values:
            normalized = self._normalize_name(value)
            if normalized:
                result.add(normalized)
        return result

    def _normalize_name(self, value: Any) -> str:
        value = str(value or "").strip().lower()
        if not value:
            return ""
        value = Path(value).name
        if "." in value:
            value = Path(value).stem
        return re.sub(r"[^a-z0-9_-]+", "", value)

    def _app_descendant_pids(self) -> dict[str, set[int]]:
        process_tree = self._process_tree()
        descendants: dict[str, set[int]] = {}
        for app_id, app in self._running_apps.items():
            if app.pid <= 0:
                pids = set(app.child_pids)
                if pids:
                    descendants[app_id] = pids
                continue
            pids = {app.pid, *app.child_pids}
            pending = [app.pid, *app.child_pids]
            while pending:
                parent = pending.pop()
                children = process_tree.get(parent, set())
                for child in children:
                    if child in pids:
                        continue
                    pids.add(child)
                    pending.append(child)
            descendants[app_id] = pids
        return descendants

    def _process_tree(self) -> dict[int, set[int]]:
        tree: dict[int, set[int]] = {}
        try:
            names = os.listdir("/proc")
        except Exception:
            return tree
        for name in names:
            if not name.isdigit():
                continue
            pid = int(name)
            ppid = self._parent_pid(pid)
            if ppid > 0:
                tree.setdefault(ppid, set()).add(pid)
        return tree

    def _parent_pid(self, pid: int) -> int:
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as handle:
                stat = handle.read()
        except Exception:
            return 0
        end = stat.rfind(")")
        if end < 0:
            return 0
        fields = stat[end + 2 :].split()
        if len(fields) < 2:
            return 0
        try:
            return int(fields[1])
        except ValueError:
            return 0

    def _owning_app_id(self, pid: int, app_descendants: dict[str, set[int]]) -> str:
        if pid <= 0:
            return ""
        for app_id, pids in app_descendants.items():
            if pid in pids:
                return app_id
        return ""

    def _group_windows(self, windows: list[WindowInfo]) -> dict[str, list[WindowInfo]]:
        groups: dict[str, list[WindowInfo]] = {}
        for window in windows:
            if not window.visible:
                continue
            groups.setdefault(window.group_key, []).append(window)
        for group_windows in groups.values():
            group_windows.sort(key=lambda window: (not self._wayland.can_manage_window(window.window_id), window.source == "running-app"))
        return groups

    def _set_groups(self, groups: dict[str, list[WindowInfo]]) -> None:
        old_keys = set(self._buttons)
        new_keys = set(groups)
        for key in sorted(old_keys - new_keys):
            button = self._buttons.pop(key)
            self._box.remove(button)

        for key in sorted(new_keys - old_keys):
            button = Gtk.Button()
            button.get_style_context().add_class("taskbar-button")
            button.connect("clicked", self._on_button_clicked, key)
            button.connect("button-press-event", self._on_button_press, key)
            self._buttons[key] = button
            self._box.pack_start(button, False, False, 0)

        self._groups = groups
        for key, button in self._buttons.items():
            self._update_button(button, groups.get(key, []))
        self.show_all()

    def _update_button(self, button: Gtk.Button, windows: list[WindowInfo]) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        first = windows[0] if windows else None
        icon = self._window_icon_image(first) if first is not None else None
        if icon is not None:
            box.pack_start(icon, False, False, 0)

        label = Gtk.Label(label=self._group_label(windows))
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_xalign(0)
        box.pack_start(label, True, True, 0)

        current = button.get_child()
        if current is not None:
            button.remove(current)
        button.add(box)
        button.set_tooltip_text("\n".join(window.title for window in windows))

        style = button.get_style_context()
        if any(window.active for window in windows):
            style.add_class("active")
        else:
            style.remove_class("active")

    def _group_label(self, windows: list[WindowInfo]) -> str:
        if not windows:
            return ""
        first = windows[0]
        app = self._apps.get(first.app_id)
        name = app.display_name if app else first.title
        if len(windows) > 1:
            return f"{name} ({len(windows)})"
        return name or first.title

    def _icon_image(self, icon_path: str) -> Gtk.Image | None:
        if not icon_path:
            return None
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                icon_path,
                self.ICON_SIZE,
                self.ICON_SIZE,
                True,
            )
        except Exception:
            return None
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_size_request(self.ICON_SIZE, self.ICON_SIZE)
        return image

    def _window_icon_image(self, window: WindowInfo) -> Gtk.Image | None:
        for icon_path in self._window_icon_paths(window):
            icon = self._icon_image(icon_path)
            if icon is not None:
                return icon

        for icon_name in self._window_icon_names(window):
            icon = self._themed_icon_image(icon_name)
            if icon is not None:
                return icon

        icon_kind, icon_value = self._desktop_icon_spec(window.app_id, window.title)
        if icon_kind == "path":
            icon = self._icon_image(icon_value)
        elif icon_kind == "theme":
            icon = self._themed_icon_image(icon_value)
        else:
            icon = None
        if icon is not None:
            return icon

        return (
            self._themed_icon_image("application-x-executable")
            or self._themed_icon_image("application-default-icon")
        )

    def _window_icon_paths(self, window: WindowInfo) -> list[str]:
        paths = []
        if window.app_id in self._apps:
            paths.append(self._apps[window.app_id].icon_path)
        if window.app_id in self._running_apps:
            paths.append(self._running_apps[window.app_id].icon_path)
        for key in ("icon_path", "iconPath", "icon", "app_icon", "appIcon"):
            value = str(window.raw.get(key) or "").strip()
            if value and (value.startswith("/") or value.startswith("~")):
                paths.append(os.path.expanduser(value))
        return [path for path in paths if path]

    def _window_icon_names(self, window: WindowInfo) -> list[str]:
        names = []
        for key in ("icon_name", "iconName", "icon", "app_icon_name", "appIconName"):
            value = str(window.raw.get(key) or "").strip()
            if value and not value.startswith("/") and not value.startswith("~"):
                names.append(value)
        return names

    def _themed_icon_image(self, icon_name: str) -> Gtk.Image | None:
        icon_name = str(icon_name or "").strip()
        if not icon_name:
            return None
        theme = Gtk.IconTheme.get_default()
        if theme is None:
            return None
        try:
            pixbuf = theme.load_icon(icon_name, self.ICON_SIZE, Gtk.IconLookupFlags.FORCE_SIZE)
        except Exception:
            return None
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_size_request(self.ICON_SIZE, self.ICON_SIZE)
        return image

    def _theme_has_icon(self, icon_name: str) -> bool:
        theme = Gtk.IconTheme.get_default()
        if theme is None:
            return False
        try:
            return bool(theme.has_icon(icon_name))
        except Exception:
            return False

    def _desktop_icon_spec(self, app_id: str, title: str = "") -> tuple[str, str]:
        app_id = str(app_id or "").strip()
        title = str(title or "").strip()
        cache_key = (app_id, title)
        if cache_key in self._desktop_icon_cache:
            return self._desktop_icon_cache[cache_key]

        desktop_app_info = getattr(Gio, "DesktopAppInfo", None)
        for desktop_id in self._desktop_id_candidates(app_id):
            try:
                app_info = desktop_app_info.new(desktop_id) if desktop_app_info is not None else None
            except Exception:
                app_info = None
            spec = self._icon_spec_from_gicon(app_info.get_icon() if app_info is not None else None)
            if spec[0]:
                self._desktop_icon_cache[cache_key] = spec
                return spec

        spec = self._desktop_file_icon_spec(app_id, title)
        self._desktop_icon_cache[cache_key] = spec
        return spec

    def _desktop_id_candidates(self, app_id: str) -> list[str]:
        values = []
        app_id = str(app_id or "").strip()
        if app_id:
            values.extend([app_id, Path(app_id).name])
            if not app_id.endswith(".desktop"):
                values.extend([f"{app_id}.desktop", f"{Path(app_id).name}.desktop"])
            normalized = self._normalize_name(app_id)
            if normalized:
                values.extend([normalized, f"{normalized}.desktop"])
        result = []
        seen = set()
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _desktop_file_icon_spec(self, app_id: str, title: str) -> tuple[str, str]:
        identity = {self._normalize_name(app_id), self._normalize_name(title)}
        identity.discard("")
        if not identity:
            return ("", "")

        for desktop_file in self._desktop_files():
            try:
                keyfile = GLib.KeyFile()
                keyfile.load_from_file(str(desktop_file), GLib.KeyFileFlags.NONE)
                icon = keyfile.get_string("Desktop Entry", "Icon")
            except Exception:
                continue
            names = {self._normalize_name(desktop_file.stem)}
            for key in ("StartupWMClass", "Name", "Exec"):
                try:
                    names.add(self._normalize_name(keyfile.get_string("Desktop Entry", key)))
                except Exception:
                    pass
            names.discard("")
            if identity.intersection(names):
                if icon.startswith("/") or icon.startswith("~"):
                    return ("path", os.path.expanduser(icon))
                return ("theme", icon)
        return ("", "")

    def _desktop_files(self) -> list[Path]:
        data_dirs = [Path.home() / ".local/share"]
        for value in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
            if value:
                data_dirs.append(Path(value))

        files = []
        for data_dir in data_dirs:
            applications = data_dir / "applications"
            try:
                files.extend(applications.rglob("*.desktop"))
            except Exception:
                continue
        return files

    def _icon_spec_from_gicon(self, icon) -> tuple[str, str]:
        if icon is None:
            return ("", "")
        try:
            if isinstance(icon, Gio.FileIcon):
                path = icon.get_file().get_path()
                return ("path", str(path or ""))
            if isinstance(icon, Gio.ThemedIcon):
                for name in icon.get_names():
                    if self._theme_has_icon(name):
                        return ("theme", str(name))
        except Exception:
            return ("", "")
        return ("", "")

    def _on_button_clicked(self, _button: Gtk.Button, group_key: str) -> None:
        windows = self._groups.get(group_key, [])
        if len(windows) == 1:
            self._activate_window(windows[0])
            return

        self._show_window_menu(windows)

    def _on_button_press(self, _button: Gtk.Button, event, group_key: str) -> bool:
        if event.button != Gdk.BUTTON_SECONDARY:
            return False
        windows = self._groups.get(group_key, [])
        self._show_window_menu(windows, management=True)
        return True

    def _show_window_menu(self, windows: list[WindowInfo], *, management: bool = False) -> None:
        menu = Gtk.Menu()
        if management:
            windows = self._manageable_menu_windows(windows)
        for window in windows:
            if management:
                self._append_management_menu(menu, window)
            else:
                item = Gtk.MenuItem(label=window.title)
                item.connect("activate", self._on_menu_item_activate, window)
                menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(None)

    def _manageable_menu_windows(self, windows: list[WindowInfo]) -> list[WindowInfo]:
        manageable = [window for window in windows if self._wayland.can_manage_window(window.window_id)]
        if manageable:
            return manageable
        return [window for window in windows if window.source != "running-app"] or list(windows[:1])

    def _append_management_menu(self, menu: Gtk.Menu, window: WindowInfo) -> None:
        title = Gtk.MenuItem(label=window.title)
        title.connect("activate", self._on_menu_item_activate, window)
        menu.append(title)
        for label, action in (
            ("Activate", "activate"),
            ("Minimize", "minimize"),
            ("Restore", "restore"),
            ("Maximize", "maximize"),
            ("Unmaximize", "unmaximize"),
            ("Close", "close"),
        ):
            can_manage = self._wayland.can_manage_window(window.window_id, action)
            if action != "activate" and not can_manage:
                continue
            item = Gtk.MenuItem(label=f"  {label}")
            item.connect("activate", self._on_manage_menu_item_activate, window, action)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())

    def _on_menu_item_activate(self, _item: Gtk.MenuItem, window: WindowInfo) -> None:
        self._activate_window(window)

    def _on_manage_menu_item_activate(self, _item: Gtk.MenuItem, window: WindowInfo, action: str) -> None:
        if action == "activate":
            self._activate_window(window)
            return
        self._manage_window(window, action)

    def _activate_window(self, window: WindowInfo) -> None:
        if self._manage_window(window, "activate"):
            return
        if window.window_id:
            self._shell.fire_and_forget("ActivateWindow", window.window_id)
            return
        if window.app_id:
            self._shell.fire_and_forget("ActivateApp", window.app_id)

    def _manage_window(self, window: WindowInfo, action: str) -> bool:
        if window.window_id and self._wayland.manage_window(window.window_id, action):
            return True
        if window.window_id:
            self._shell.fire_and_forget("ManageWindow", window.window_id, action)
            return True
        return False


def main() -> int:
    Taskbar().show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
