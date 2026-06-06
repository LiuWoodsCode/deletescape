import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtCore import Qt

from app_registry import AppDescriptor, discover_apps, load_app_class

import sys
import os
import traceback
import time
import gc
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from battery import get_battery_info
from telephony import get_signal_strength

from logger import PROCESS_START, get_logger

from config import ConfigStore, OSConfig, DeviceConfigStore, DeviceConfig
from fs_layout import get_user_data_layout
from app_registry import AppDescriptor, discover_apps, load_app_class, unload_app_modules

from PySide6.QtCore import Qt, QTimer, QRectF, QObject, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush, QImage, QPixmap
from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QFrame, QGraphicsOpacityEffect, QSizePolicy

from buttons import ButtonAction, ButtonBinding, ButtonManager

from photo_picker import request_photo_from_gallery
from wallpaper import load_pixmap, scale_crop_center

from background_tasks import BackgroundTaskManager
from taskbar import Taskbar

log = get_logger("continuity")
# ---------------------------------------------------------
# MAIN SHELL (NO MDI)
# ---------------------------------------------------------
class NativeShell(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Deletescape Shell (Native Windowing)")
        self.resize(1280, 800)

        # Simple central layout (no desktop surface)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Placeholder (you can later add wallpaper widget here if desired)
        self.desktop_placeholder = QWidget()
        self.desktop_placeholder.setStyleSheet("background: black;")
        central_layout.addWidget(self.desktop_placeholder)

        # Taskbar stays
        self.taskbar = Taskbar(self)
        central_layout.addWidget(self.taskbar)

        self.setCentralWidget(central)

        self.apps: dict[str, AppDescriptor] = self.load_apps()
        
        self._config_store = ConfigStore()
        self.config: OSConfig = self._config_store.load()
        log.debug(
            "Config loaded",
            extra={
                "dark_mode": bool(getattr(self.config, "dark_mode", False)),
                "use_24h_time": bool(getattr(self.config, "use_24h_time", True)),
                "lock_wallpaper": str(getattr(self.config, "lock_wallpaper", "")),
                "home_wallpaper": str(getattr(self.config, "home_wallpaper", "")),
            },
        )

        self._device_config_store = DeviceConfigStore()
        self.device: DeviceConfig = self._device_config_store.load()
        log.debug(
            "DeviceConfig loaded",
            extra={
                "manufacturer": str(getattr(self.device, "manufacturer", "")),
                "model": str(getattr(self.device, "model", "")),
                "has_hw_home": bool(getattr(self.device, "has_hw_home", True)),
            },
        )

        self.active_app = None
        self.active_app_id: str | None = None
        self._control_center_open = False
        self._handling_crash = False
        self._locked = True
        self._has_unlocked_once = False

        # Background scheduler for apps.
        self.background_tasks = BackgroundTaskManager(window=self)

        # Load available apps from the apps/ folder (folder-based apps)
        self.apps: dict[str, AppDescriptor] = self.load_apps()
        log.info("Apps loaded", extra={"count": len(self.apps)})

        # Running apps (real OS windows now)
        self._running: dict[str, QMainWindow] = {}

    # ---------------------------------------------------------
    # App discovery
    # ---------------------------------------------------------

    def load_apps(self):
        base_dir = Path(__file__).resolve().parent
        builtin_apps_root = base_dir / "apps"
        user_apps_root = get_user_data_layout(base_dir).applications

        log.debug(
            "Loading apps",
            extra={"builtin_apps_root": str(builtin_apps_root), "user_apps_root": str(user_apps_root)},
        )

        builtins = discover_apps(builtin_apps_root)
        user_apps = discover_apps(user_apps_root)

        duplicates = set(builtins.keys()) & set(user_apps.keys())
        if duplicates:
            log.warning("User app IDs conflict with built-in apps; built-ins take precedence", extra={"app_ids": sorted(duplicates)})

        merged = dict(user_apps)
        merged.update(builtins)
        return merged

    # ---------------------------------------------------------
    # Launch app (native window)
    # ---------------------------------------------------------
    def launch_app(self, app_id: str):
        if app_id not in self.apps:
            QMessageBox.warning(self, "Unknown App", f"No app with id '{app_id}'")
            return

        # Already running → raise window
        if app_id in self._running:
            win = self._running.get(app_id)
            if win:
                win.show()
                win.raise_()
                win.activateWindow()
                return

        desc = self.apps[app_id]

        try:
            if desc.app_class is None:
                desc.app_class = load_app_class(desc)

            app_class = desc.app_class
            if app_class is None:
                raise RuntimeError("App class could not be loaded")

            # ✅ Real OS-level window
            window = QMainWindow()
            window.setAttribute(Qt.WA_DeleteOnClose, True)
            window.setWindowFlags(Qt.Window)

            container = QWidget()
            window.setCentralWidget(container)

            # Instantiate app
            instance = app_class(window=self, container=container)

            window.setWindowTitle(desc.display_name or app_id)
            window.resize(900, 600)

            window.show()

            # Track
            self._running[app_id] = window

            def _on_close():
                try:
                    self._running.pop(app_id, None)
                except Exception:
                    pass
                try:
                    self.taskbar.refresh()
                except Exception:
                    pass

            window.destroyed.connect(_on_close)

            self.taskbar.refresh()

        except Exception as e:
            print(e)
            QMessageBox.critical(
                self,
                "App Launch Failed",
                f"Failed to launch '{app_id}':\n\n{e}",
            )

    def _autostart_apps(self) -> None:
        try:
            autostart_ids = [a.app_id for a in self.apps.values() if bool(getattr(a, "autostart", False))]
        except Exception:
            autostart_ids = []

        if not autostart_ids:
            return

        log.info("Autostart apps", extra={"count": len(autostart_ids), "app_ids": list(autostart_ids)})

        for app_id in autostart_ids:
            try:
                running = self._get_or_start_app(app_id)
                if running is None:
                    continue

                # Keep service apps alive even when not foreground.
                running.background_enabled = True

                # Optional: allow service apps to perform post-init wiring.
                try:
                    hook = getattr(running.instance, "on_autostart", None)
                    if callable(hook):
                        hook()
                except Exception:
                    log.exception("Autostart hook failed", extra={"app_id": str(app_id)})
            except Exception:
                log.exception("Failed to autostart app", extra={"app_id": str(app_id)})

    def show_startup_lock_screen(self) -> None:
        """Show the initial lock screen overlay and log startup timing once."""
        try:
            self._locked = True
            self._show_lock_overlay(True)
            log.info("Device starts locked")
        except Exception:
            log.exception("Failed to show startup lock screen")

        try:
            dt_ms = int((time.perf_counter() - PROCESS_START) * 1000)
            log.info("Startup timing", extra={"to_lock_screen_ms": dt_ms})
        except Exception:
            log.exception("Failed to log startup timing")

    def format_time(self, dt: datetime) -> str:
        if self.config.use_24h_time:
            return dt.strftime('%H:%M')
        # 12-hour without leading zero on Windows.
        return dt.strftime('%I:%M %p').lstrip('0')

    def set_setting(self, key: str, value):
        if not hasattr(self.config, key):
            log.debug("Ignoring unknown setting", extra={"key": str(key)})
            return
        log.info("Setting changed", extra={"key": str(key), "value": value})
        setattr(self.config, key, value)
        self._config_store.save(self.config)

        # Apply changes immediately.
        if key == 'dark_mode':
            self.apply_theme()
            try:
                self.notifications.set_dark_mode(bool(self.config.dark_mode))
            except Exception:
                pass
        if key in {'lock_wallpaper', 'home_wallpaper'}:
            self.apply_wallpapers()

    def apply_wallpapers(self) -> None:
        try:
            if hasattr(self, 'lock_screen'):
                self.lock_screen.set_wallpaper_path(getattr(self.config, 'lock_wallpaper', '') or '')
        except Exception:
            log.exception("Failed to apply lock wallpaper")
            pass

    def apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return

        log.debug("Apply theme", extra={"dark_mode": bool(getattr(self.config, "dark_mode", False))})

        # Minimal dark palette for readability.
        app.setStyle('FluentWinUi3')
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt

        app = QGuiApplication.instance()

        if self.config.dark_mode:
            if not os.name == "nt":
                palette = QPalette()
                palette.setColor(QPalette.Window, QColor(53, 53, 53))
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
            app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        else:
            app.styleHints().setColorScheme(Qt.ColorScheme.Light)

    def run_on_ui_thread(self, fn) -> None:
        """Run callable on the Qt UI thread (safe from worker threads)."""

        try:
            app = QApplication.instance()
            if app is None:
                fn()
                return

            if QThread.currentThread() == app.thread():
                fn()
                return

            self._ui_dispatcher._invoke.emit(fn)
        except Exception:
            # Best-effort fallback.
            try:
                fn()
            except Exception:
                pass

    def _notify_ui(self, *, title: str, message: str = "", duration_ms: int = 3500, app_id: str | None = None) -> None:
        """UI-thread-only notification implementation."""
        if app_id is None:
            app_id = self.active_app_id or ""

        log.debug(
            "Notify",
            extra={
                "app_id": str(app_id or ""),
                "title": str(title or ""),
                "message_len": len(str(message or "")),
                "duration_ms": int(duration_ms),
            },
        )

        try:
            # Create a banner and add it to the bottom-right stacked layout.
            banner = NotificationBanner(title or "", message or "", duration_ms, parent=self._notifications_area)

            # Constrain width so long messages wrap instead of overflowing.
            try:
                # Allow banners to occupy up to half the window width, capped
                # to a sensible maximum for large displays, and with a comfortable
                # minimum so very small windows still show readable text.
                max_w = min(640, max(360, int(self.width() * 0.5)))
            except Exception:
                max_w = 480
            banner.setMaximumWidth(max_w)
            banner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            # Also allow a reasonable minimum width so short messages don't
            # produce a tiny, narrow box.
            try:
                banner.setMinimumWidth(min(320, max_w))
            except Exception:
                pass

            # Add aligned to right; layout alignment set to bottom/right.
            self._notifications_layout.addWidget(banner, 0, Qt.AlignRight)
            banner.show()
            self._notifications_area.raise_()
        except Exception:
            log.exception("Failed to show desktop notification", extra={"title": title, "app_id": app_id})

    def notify(self, *, title: str, message: str = "", duration_ms: int = 3500, app_id: str | None = None) -> None:
        """Show a transient banner below the status bar.

        Thread-safe: may be called from background threads.
        """

        self.run_on_ui_thread(lambda: self._notify_ui(title=title, message=message, duration_ms=duration_ms, app_id=app_id))

    def enable_background(self, enabled: bool = True, *, app_id: str | None = None) -> None:
        """Opt the given app into staying alive when not foreground."""

        if app_id is None:
            app_id = self.active_app_id
        if not app_id:
            return
        running = self._running_apps.get(app_id)
        if running is None:
            return

        log.info("Background mode updated", extra={"app_id": str(app_id), "enabled": bool(enabled)})
        running.background_enabled = bool(enabled)

    def register_background_task(
        self,
        callback,
        *,
        interval_ms: int = 1000,
        name: str = "background_task",
        app_id: str | None = None,
        start_immediately: bool = False,
    ):
        """Register a periodic callback to run after first unlock."""

        if app_id is None:
            app_id = self.active_app_id
        if not app_id:
            app_id = ""

        log.debug(
            "Register background task via API",
            extra={"app_id": str(app_id), "task_name": str(name), "interval_ms": int(interval_ms), "start_immediately": bool(start_immediately)},
        )
        return self.background_tasks.register(
            app_id=str(app_id),
            callback=callback,
            interval_ms=interval_ms,
            name=name,
            start_immediately=start_immediately,
        )

    # ---------------------------------------------------------
    # App discovery (same mechanism)
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Launch app into an MDI subwindow
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def launch_all_apps(self):
        for app_id in self.apps.keys():
            self.launch_app(app_id)

    def get_visible_apps(self):
        return [app for app in self.apps.values() if not app.hidden]

    def get_all_apps(self):
        return list(self.apps.values())


# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    shell = NativeShell()
    shell.launch_app(str(sys.argv[1]))
    sys.exit(app.exec())