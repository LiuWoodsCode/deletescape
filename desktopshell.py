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


class NotificationBanner(QFrame):
    """Small transient notification banner used by the desktop shell.

    Appears in the bottom-right of the main window and dismisses itself
    after `duration_ms` milliseconds.
    """

    def __init__(self, title: str, message: str, duration_ms: int = 3500, parent=None):
        super().__init__(parent)
        self.setObjectName("desktop_notification")

        self.setStyleSheet(
            "QFrame#desktop_notification{background-color: rgba(40,40,40,230); color: white; border-radius: 8px; padding: 8px;}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title_label = QLabel(title)
        f = QFont()
        f.setBold(True)
        title_label.setFont(f)
        title_label.setStyleSheet("color: white;")

        msg_label = QLabel(message)
        msg_label.setStyleSheet("color: white;")
        msg_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(msg_label)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)

        # Fade-in
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_close)
        self._timer.start(int(duration_ms))

        # Make banner horizontally constrained so text wraps nicely
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _start_close(self):
        # Fade-out then delete
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()

    def mousePressEvent(self, event):
        try:
            if hasattr(self, '_timer') and self._timer.isActive():
                self._timer.stop()
            self._start_close()
        except Exception:
            pass

from PySide6.QtWidgets import QApplication, QMainWindow, QMdiArea
from PySide6.QtGui import QBrush, QPixmap
from PySide6.QtCore import Qt
import sys

class ImageMdiArea(QMdiArea):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self._orig = QPixmap(image_path)
        self._scaled = QPixmap()
        self._update_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_background()

    def _update_background(self):
        if self._orig.isNull():
            return
        # Choose how you want it scaled:
        target_size = self.viewport().size()
        # KeepAspectRatioByExpanding fills and crops; use KeepAspectRatio to letterbox instead
        scaled = self._orig.scaled(
            target_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        self._scaled = scaled
        # Apply as background brush (no tiling because it matches the viewport)
        try:
            # Preferred API on QMdiArea
            self.setBackground(QBrush(self._scaled))
        except AttributeError:
            # Fallback: set on viewport palette if setBackground isn't available
            pal = self.viewport().palette()
            pal.setBrush(pal.Window, QBrush(self._scaled))
            self.viewport().setAutoFillBackground(True)
            self.viewport().setPalette(pal)
            
class MdiShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deletescape MDI Shell (Minimal)")
        self.showFullScreen()
        # self.show()
        # Central MDI area
        self.mdi = ImageMdiArea(".\\assets\\wallpaper\\test_desktopshell_wal.png")
        self.mdi.setViewMode(QMdiArea.SubWindowView)
        self.mdi.setOption(QMdiArea.DontMaximizeSubWindowOnActivation, True)
        self.mdi.subWindowActivated.connect(self._on_subwindow_activated)
        

        self.mdi.setStyleSheet("""
        QMdiArea {
            background: transparent;
        }
        QMdiArea > QWidget#qt_scrollarea_viewport {
            background-image: url(./background.png);
            background-position: center;
            background-repeat: no-repeat;
        }
        """)

        # Build a central widget that contains the MDI area and a taskbar at the bottom.
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.mdi)

        # create taskbar (will be refreshed after apps load)
        self.taskbar = Taskbar(self)
        central_layout.addWidget(self.taskbar)

        self.setCentralWidget(central)

        # Notification overlay area (bottom-right stacked banners)
        self._notifications_area = QWidget(self)
        self._notifications_area.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._notifications_layout = QVBoxLayout(self._notifications_area)
        self._notifications_layout.setContentsMargins(10, 10, 10, 56)
        self._notifications_layout.setSpacing(6)
        # Stack widgets from bottom to top, aligned right
        self._notifications_layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        self._notifications_area.setLayout(self._notifications_layout)
        self._notifications_area.setGeometry(self.rect())
        self._notifications_area.raise_()

        self.apps: dict[str, AppDescriptor] = self.load_apps()
        self._running: dict[str, QMdiSubWindow] = {}
        
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

        # Refresh taskbar to reflect available/running apps
        try:
            self.taskbar.refresh()
        except Exception:
            pass

        # Autostart background/service apps (does not change foreground app).
        self._autostart_apps()

        # Apply persisted UI preferences after QApplication exists.
        self.apply_theme()
        self.apply_wallpapers()

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
    def load_apps(self):
        # project root = phoneos/phoneos
        project_root = Path(__file__).resolve().parents[0]
        builtin_root = project_root / "apps"

        if not builtin_root.is_dir():
            raise RuntimeError(f"Apps root missing: {builtin_root}")

        return discover_apps(builtin_root)

    # ---------------------------------------------------------
    # Launch app into an MDI subwindow
    # ---------------------------------------------------------
    def launch_app(self, app_id: str):
        if app_id not in self.apps:
            QMessageBox.warning(self, "Unknown App", f"No app with id '{app_id}'")
            return

        # If already running, just activate
        if app_id in self._running:
            sub = self._running.get(app_id)
            try:
                if sub is not None and sub.isVisible():
                    self.mdi.setActiveSubWindow(sub)
                    return
            except Exception:
                pass

            # Stale reference (closed/hidden) -> drop and relaunch cleanly.
            self._running.pop(app_id, None)

        desc = self.apps[app_id]

        try:
            if desc.app_class is None:
                desc.app_class = load_app_class(desc)

            app_class = desc.app_class
            if app_class is None:
                raise RuntimeError("App class could not be loaded")

            sub = QMdiSubWindow()
            sub.setAttribute(Qt.WA_DeleteOnClose, True)

            # this is the real container the app expects
            container = QWidget()
            sub.setWidget(container)

            instance = app_class(window=self, container=container)

            # Title
            sub.setWindowTitle(desc.display_name or app_id)

            # Add to MDI
            self.mdi.addSubWindow(container)
            container.resize(480, 600)
            container.show()

            # Track running QMdiSubWindow (store sub, not the inner container)
            self._running[app_id] = container

            # Cleanup tracking on close and refresh taskbar
            def _on_destroy(aid=app_id):
                try:
                    self._running.pop(aid, None)
                except Exception:
                    pass
                try:
                    self.taskbar.refresh()
                except Exception:
                    pass

            sub.destroyed.connect(_on_destroy)

            # Make sure taskbar reflects the new running app
            try:
                self.taskbar.refresh()
            except Exception:
                pass

        except Exception as e:
            QMessageBox.critical(
                self,
                "App Launch Failed",
                f"Failed to launch '{app_id}':\n\n{e}",
            )

    # ---------------------------------------------------------
    # Convenience: launch all visible apps at once (demo mode)
    # ---------------------------------------------------------
    def launch_all_apps(self):
        for app_id in self.apps.keys():
            self.launch_app(app_id)
            
    # Helper to return apps that are not marked hidden
    def get_visible_apps(self):
        return [app for app in self.apps.values() if not app.hidden]
    
    def get_all_apps(self):
        return [app for app in self.apps.values()]

    def _on_subwindow_activated(self, sub):
        # Update active_app_id when MDI activation changes and refresh taskbar
        active_id = None
        try:
            for aid, s in self._running.items():
                if s is sub:
                    active_id = aid
                    break
        except Exception:
            active_id = None

        self.active_app_id = active_id
        try:
            self.taskbar.refresh()
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            # Keep notifications overlay sized to the window
            if hasattr(self, '_notifications_area') and self._notifications_area is not None:
                self._notifications_area.setGeometry(self.rect())
        except Exception:
            pass
        return super().resizeEvent(event)

    def is_setup_completed(self) -> bool:
        return bool(getattr(self.config, "setup_completed", False))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    shell = MdiShell()
    # shell.showFullScreen()

    sys.exit(app.exec())