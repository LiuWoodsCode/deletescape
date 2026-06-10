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
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell


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
    HEIGHT = 48
    ICON_SIZE = 32

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
        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(self._box)

        left_spacer = Gtk.Box()
        right_spacer = Gtk.Box()
        left_spacer.set_hexpand(True)
        right_spacer.set_hexpand(True)

        self._task_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._task_group.set_halign(Gtk.Align.CENTER)

        self._apps_button = Gtk.Button(label="Apps")
        self._apps_button.get_style_context().add_class("apps-button")
        self._apps_button.set_tooltip_text("Apps")
        self._task_group.pack_start(self._apps_button, False, False, 0)

        self._task_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._task_group.pack_start(self._task_box, False, False, 0)

        self._box.pack_start(left_spacer, True, True, 0)
        self._box.pack_start(self._task_group, False, False, 0)
        self._box.pack_start(right_spacer, True, True, 0)

    def _install_css(self) -> None:
        css = b"""
        window {
            background: #202020;
            color: white;
            font-size: 12px;
        }
        button.taskbar-button,
        button.apps-button {
            background: #303030;
            border: 1px solid #505050;
            border-radius: 0;
            color: white;
            min-height: 28px;
            padding: 1px 6px;
        }
        button.taskbar-button {
            min-width: 34px;
        }
        button.apps-button {
            min-width: 64px;
            padding: 1px 10px;
        }
        button.taskbar-button:hover,
        button.apps-button:hover {
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

def main() -> int:
    Taskbar().show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
