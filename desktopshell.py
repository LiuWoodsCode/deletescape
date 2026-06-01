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
import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from battery import get_battery_info
from audio import get_audio_info
from telephony import get_signal_strength
from wifi import get_wifi_info

from logger import PROCESS_START, get_logger

from config import ConfigStore, OSConfig, DeviceConfigStore, DeviceConfig
from fs_layout import get_user_data_layout
from app_registry import AppDescriptor, discover_apps, load_app_class, unload_app_modules
from media import MediaSession, MediaSessionManager
from notifications import NotificationCenter

from PySide6.QtCore import Qt, QTimer, QRectF, QObject, QThread, Signal, QEvent
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush, QImage, QPixmap
from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QFrame,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QScrollArea,
    QGridLayout,
    QProgressBar,
)

from buttons import ButtonAction, ButtonBinding, ButtonManager

from photo_picker import request_photo_from_gallery
from wallpaper import load_pixmap, scale_crop_center

from background_tasks import BackgroundTaskManager
from taskbar import Taskbar

log = get_logger("continuity")


class _MainThreadDispatcher(QObject):
    _invoke = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._invoke.connect(self._run, type=Qt.QueuedConnection)

    def _run(self, fn) -> None:
        try:
            fn()
        except Exception:
            pass


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


class ControlCenterTile(QFrame):
    def __init__(self, title: str, value: str = "", detail: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ccTile")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(82)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("ccTileTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("ccTileValue")
        self.value_label.setWordWrap(True)
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("ccTileDetail")
        self.detail_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_values(self, value: str, detail: str = "") -> None:
        self.value_label.setText(str(value or ""))
        self.detail_label.setText(str(detail or ""))
        self.detail_label.setVisible(bool(str(detail or "").strip()))


class DesktopMediaCard(QFrame):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self._session: MediaSession | None = None
        self.setObjectName("ccMediaCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)
        root.addLayout(top)

        self.art_label = QLabel("Media")
        self.art_label.setObjectName("ccMediaArt")
        self.art_label.setFixedSize(58, 58)
        self.art_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self.art_label, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        top.addLayout(text, 1)

        self.heading_label = QLabel("No media playing")
        self.heading_label.setObjectName("ccMediaTitle")
        self.heading_label.setWordWrap(True)
        text.addWidget(self.heading_label)

        self.sub_label = QLabel("Start playback in an app to show controls here.")
        self.sub_label.setObjectName("ccSubText")
        self.sub_label.setWordWrap(True)
        text.addWidget(self.sub_label)

        self.app_label = QLabel("")
        self.app_label.setObjectName("ccSubText")
        self.app_label.setWordWrap(True)
        text.addWidget(self.app_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("ccMediaProgress")
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        root.addLayout(controls)

        self.prev_btn = self._button("Previous", "previous")
        self.play_btn = self._button("Play", "play")
        self.next_btn = self._button("Next", "next")
        controls.addStretch(1)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addStretch(1)

        self.set_session(None)

    def _button(self, text: str, command: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("ccMediaButton")
        btn.clicked.connect(lambda _checked=False, c=command: self._send_command(c))
        return btn

    def _send_command(self, command: str) -> None:
        if self._session is None:
            return
        try:
            self.window.send_media_command(command, app_id=self._session.app_id)
        except Exception:
            pass

    def set_session(self, session: MediaSession | None) -> None:
        self._session = session
        has_session = session is not None
        if not has_session:
            self.heading_label.setText("No media playing")
            self.sub_label.setText("Start playback in an app to show controls here.")
            self.app_label.clear()
            self.art_label.clear()
            self.art_label.setText("Media")
            self.progress.setVisible(False)
            for btn in (self.prev_btn, self.play_btn, self.next_btn):
                btn.setEnabled(False)
            return

        self.heading_label.setText(session.title or "Now playing")
        parts = [p for p in (session.artist, session.album) if str(p or "").strip()]
        self.sub_label.setText(" - ".join(parts) if parts else str(session.playback_state or "Media session").title())
        self.app_label.setText(self._app_name(session.app_id))
        self._set_artwork(session)
        self._set_progress(session)
        self._set_controls(session)

    def _app_name(self, app_id: str) -> str:
        try:
            desc = self.window.apps.get(app_id)
            if desc is not None:
                return desc.display_name or app_id
        except Exception:
            pass
        return app_id

    def _set_artwork(self, session: MediaSession) -> None:
        pixmap = QPixmap()
        artwork = Path(str(session.artwork_path or ""))
        if artwork.is_file():
            pixmap = QPixmap(str(artwork))
        if pixmap.isNull():
            try:
                desc = self.window.apps.get(session.app_id)
                icon_path = getattr(desc, "icon_path", None) if desc is not None else None
                if icon_path:
                    pixmap = QPixmap(str(icon_path))
            except Exception:
                pass
        if pixmap.isNull():
            self.art_label.clear()
            self.art_label.setText("Media")
            return
        self.art_label.setText("")
        self.art_label.setPixmap(pixmap.scaled(self.art_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

    def _set_progress(self, session: MediaSession) -> None:
        if session.duration_ms and session.position_ms is not None:
            value = max(0, min(1000, int((float(session.position_ms) / float(session.duration_ms)) * 1000.0)))
            self.progress.setValue(value)
            self.progress.setVisible(True)
            return
        self.progress.setVisible(False)

    def _set_controls(self, session: MediaSession) -> None:
        is_playing = session.playback_state == "playing"
        command = "pause" if is_playing else "play"
        if not session.supports(command) and session.supports("toggle_play_pause"):
            command = "toggle_play_pause"
        self.play_btn.setText("Pause" if is_playing else "Play")
        try:
            self.play_btn.clicked.disconnect()
        except Exception:
            pass
        self.play_btn.clicked.connect(lambda _checked=False, c=command: self._send_command(c))
        self.prev_btn.setEnabled(session.supports("previous"))
        self.play_btn.setEnabled(session.supports(command))
        self.next_btn.setEnabled(session.supports("next"))


class DesktopNotificationRow(QFrame):
    def __init__(self, notification: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ccNotification")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        layout.addLayout(top)

        app_name = str(notification.get("name") or notification.get("app_id") or "Notification")
        title = str(notification.get("title") or "Notification")
        message = str(notification.get("message") or "")

        app_label = QLabel(app_name)
        app_label.setObjectName("ccSubText")
        time_label = QLabel(self._format_time(notification.get("timestamp")))
        time_label.setObjectName("ccSubText")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(app_label)
        top.addStretch(1)
        top.addWidget(time_label)

        title_label = QLabel(title)
        title_label.setObjectName("ccNotificationTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        if message:
            message_label = QLabel(message)
            message_label.setObjectName("ccSubText")
            message_label.setWordWrap(True)
            layout.addWidget(message_label)

    def _format_time(self, raw_timestamp) -> str:
        try:
            ts = datetime.fromisoformat(str(raw_timestamp or ""))
            seconds = max(0, int((datetime.now() - ts).total_seconds()))
            if seconds < 60:
                return "Just now"
            if seconds < 3600:
                return f"{seconds // 60}m ago"
            if seconds < 86400:
                return f"{seconds // 3600}h ago"
            return f"{seconds // 86400}d ago"
        except Exception:
            return ""


class DesktopControlCenter(QFrame):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("desktopControlCenter")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(360, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        root.addLayout(header)

        self.time_label = QLabel("")
        self.time_label.setObjectName("ccTime")
        header.addWidget(self.time_label)
        header.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("ccCloseButton")
        close_btn.clicked.connect(self.window.close_control_center)
        header.addWidget(close_btn)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        root.addLayout(grid)

        self.wifi_tile = ControlCenterTile("Wi-Fi")
        self.bluetooth_tile = ControlCenterTile("Bluetooth", "Available")
        self.audio_tile = ControlCenterTile("Audio")
        self.battery_tile = ControlCenterTile("Battery")
        grid.addWidget(self.wifi_tile, 0, 0)
        grid.addWidget(self.bluetooth_tile, 0, 1)
        grid.addWidget(self.audio_tile, 1, 0)
        grid.addWidget(self.battery_tile, 1, 1)

        self.media_card = DesktopMediaCard(window=self.window, parent=self)
        root.addWidget(self.media_card)

        notif_header = QLabel("Recent notifications")
        notif_header.setObjectName("ccSectionTitle")
        root.addWidget(notif_header)

        self.notification_scroll = QScrollArea()
        self.notification_scroll.setWidgetResizable(True)
        self.notification_scroll.setObjectName("ccNotificationScroll")
        root.addWidget(self.notification_scroll, 1)

        self.notification_container = QWidget()
        self.notification_layout = QVBoxLayout(self.notification_container)
        self.notification_layout.setContentsMargins(0, 0, 0, 0)
        self.notification_layout.setSpacing(8)
        self.notification_scroll.setWidget(self.notification_container)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(3000)

        try:
            self.window.media_sessions.session_changed.connect(self.media_card.set_session)
        except Exception:
            pass

        self.setStyleSheet("""
        QFrame#desktopControlCenter {
            background-color: rgba(32, 32, 32, 245);
            color: #f3f3f3;
            border: 1px solid rgba(255, 255, 255, 36);
            border-radius: 8px;
        }
        QFrame#ccTile,
        QFrame#ccMediaCard,
        QFrame#ccNotification {
            background-color: #2d2d2d;
            border: 1px solid #3d3d3d;
            border-radius: 8px;
        }
        QLabel#ccTime {
            color: #ffffff;
            font-size: 18px;
            font-weight: 600;
        }
        QLabel#ccSectionTitle,
        QLabel#ccTileTitle,
        QLabel#ccMediaTitle,
        QLabel#ccNotificationTitle {
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
        }
        QLabel#ccTileValue {
            color: #ffffff;
            font-size: 16px;
            font-weight: 650;
        }
        QLabel#ccSubText,
        QLabel#ccTileDetail {
            color: #b8b8b8;
            font-size: 11px;
        }
        QLabel#ccMediaArt {
            color: #d6d6d6;
            background-color: #3a3a3a;
            border-radius: 8px;
            font-size: 10px;
            font-weight: 650;
        }
        QPushButton#ccMediaButton,
        QPushButton#ccCloseButton {
            min-height: 28px;
            padding: 4px 10px;
        }
        QScrollArea#ccNotificationScroll {
            background-color: transparent;
            border: none;
        }
        QProgressBar#ccMediaProgress {
            border: none;
            background-color: #484848;
            border-radius: 3px;
            height: 6px;
            max-height: 6px;
        }
        QProgressBar#ccMediaProgress::chunk {
            background-color: #f2f2f2;
            border-radius: 3px;
        }
        """)

        self.refresh()

    def refresh(self) -> None:
        self._update_time()
        self._update_status_tiles()
        self.media_card.set_session(self.window.get_active_media_session())
        self._load_notifications()

    def _update_time(self) -> None:
        now = datetime.now()
        try:
            self.time_label.setText(f"{self.window.format_time(now)}   {now.strftime('%b %d')}")
        except Exception:
            self.time_label.setText(now.strftime("%H:%M   %b %d"))

    def _update_status_tiles(self) -> None:
        try:
            wifi = self.window.get_wifi_info()
            if bool(getattr(wifi, "connected", False)):
                detail = ""
                if getattr(wifi, "signal_percent", None) is not None:
                    detail = f"{int(wifi.signal_percent)}% signal"
                self.wifi_tile.set_values(str(getattr(wifi, "ssid", "") or "Connected"), detail)
            elif getattr(wifi, "enabled", None) is False:
                self.wifi_tile.set_values("Off", "")
            else:
                self.wifi_tile.set_values("Not connected", "")
        except Exception:
            self.wifi_tile.set_values("Unavailable", "")

        try:
            device = getattr(getattr(self.window, "device", None), "bluetooth_mac", "")
            self.bluetooth_tile.set_values("On", str(device or "No connected devices"))
        except Exception:
            self.bluetooth_tile.set_values("Available", "No connected devices")

        try:
            audio = self.window.get_audio_info()
            volume = getattr(audio, "volume_percent", None)
            muted = bool(getattr(audio, "muted", False))
            output = str(getattr(audio, "output_device_name", "") or getattr(audio, "output_route", "") or "Default output")
            if volume is None:
                self.audio_tile.set_values("Default", output)
            else:
                self.audio_tile.set_values("Muted" if muted else f"{int(volume)}%", output)
        except Exception:
            self.audio_tile.set_values("Unavailable", "")

        try:
            battery = self.window.get_battery_info()
            percent = getattr(battery, "percentage", None)
            charging = bool(getattr(battery, "is_charging", False))
            self.battery_tile.set_values("Unknown" if percent is None else f"{int(percent)}%", "Charging" if charging else "On battery")
        except Exception:
            self.battery_tile.set_values("Unavailable", "")

    def _load_notifications(self) -> None:
        while self.notification_layout.count():
            item = self.notification_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        notifications = []
        path = Path("./userdata/Data/System/notifications.json")
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, list):
                        notifications = [n for n in raw if isinstance(n, dict)]
        except Exception:
            notifications = []

        for notification in list(reversed(notifications))[:5]:
            self.notification_layout.addWidget(DesktopNotificationRow(notification, self.notification_container))

        if not notifications:
            empty = QLabel("No recent notifications")
            empty.setObjectName("ccSubText")
            empty.setAlignment(Qt.AlignCenter)
            self.notification_layout.addWidget(empty)

        self.notification_layout.addStretch(1)
            
class MdiShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = self
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

        self.notifications = NotificationCenter(window=self, parent=self, banner_height_px=73)

        self.apps: dict[str, AppDescriptor] = self.load_apps()
        self._running: dict[str, QMdiSubWindow] = {}
        self._running_instances: dict[str, object] = {}
        self._running_apps = self._running
        
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
        self._control_center_subwindow: QMdiSubWindow | None = None
        self._control_center_click_filter: QObject | None = None
        self._handling_crash = False
        self._locked = True
        self._has_unlocked_once = True

        self._ui_dispatcher = _MainThreadDispatcher(self)

        self._sync_notification_geometry()

        # Background scheduler for apps.
        self.background_tasks = BackgroundTaskManager(window=self)
        self.media_sessions = MediaSessionManager(self)

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

    def open_control_center(self) -> None:
        try:
            existing = self._control_center_subwindow
            if existing is not None and existing.isVisible():
                self.close_control_center()
                return
        except Exception:
            pass

        try:
            panel = DesktopControlCenter(window=self)
            sub = self.mdi.addSubWindow(panel)
            sub.setAttribute(Qt.WA_DeleteOnClose, True)
            sub.setWindowTitle("Control Center")
            sub.setWindowFlags(sub.windowFlags() | Qt.FramelessWindowHint)
            self._control_center_subwindow = sub
            self._control_center_open = True

            def _cleanup():
                self._control_center_open = False
                self._control_center_subwindow = None
                try:
                    if self._control_center_click_filter is not None:
                        self.mdi.removeEventFilter(self._control_center_click_filter)
                except Exception:
                    pass
                self._control_center_click_filter = None

            sub.destroyed.connect(_cleanup)

            panel.resize(390, 560)
            sub.resize(panel.size())
            self._position_control_center(sub)
            sub.show()
            sub.raise_()

            self._install_control_center_click_away(sub)
        except Exception:
            log.exception("Failed to open desktop control center")

    def close_control_center(self) -> None:
        try:
            sub = self._control_center_subwindow
            if sub is not None:
                sub.close()
        except Exception:
            try:
                if self._control_center_subwindow is not None:
                    self._control_center_subwindow.hide()
            except Exception:
                pass
        self._control_center_open = False

    def toggle_control_center(self) -> None:
        self.open_control_center()

    def _position_control_center(self, sub: QMdiSubWindow | None = None) -> None:
        try:
            if sub is None:
                sub = self._control_center_subwindow
            if sub is None:
                return

            margin = 10
            available_w = max(1, self.mdi.width())
            available_h = max(1, self.mdi.height())
            width = min(390, max(320, available_w - (margin * 2)))
            height = min(560, max(420, available_h - (margin * 2)))
            sub.resize(width, height)
            x = max(margin, available_w - width - margin)
            y = max(margin, available_h - height - margin)
            sub.move(x, y)
        except Exception:
            pass

    def _install_control_center_click_away(self, sub: QMdiSubWindow) -> None:
        try:
            if self._control_center_click_filter is not None:
                self.mdi.removeEventFilter(self._control_center_click_filter)
        except Exception:
            pass

        shell = self

        class _ControlCenterClickAway(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)

            def eventFilter(self, obj, event):
                try:
                    if event.type() == QEvent.MouseButtonPress:
                        current = shell._control_center_subwindow
                        if current is not None and not current.geometry().contains(event.pos()):
                            shell.close_control_center()
                except Exception:
                    pass
                return False

        self._control_center_click_filter = _ControlCenterClickAway(self.mdi)
        self.mdi.installEventFilter(self._control_center_click_filter)

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
            self._sync_notification_geometry()
            self.notifications.notify(
                title=title or "",
                message=message or "",
                duration_ms=duration_ms,
                app_id=str(app_id or ""),
            )
        except Exception:
            log.exception("Failed to show desktop notification", extra={"title": title, "app_id": app_id})

    def notify(self, *, title: str, message: str = "", duration_ms: int = 3500, app_id: str | None = None) -> None:
        """Show a transient banner below the status bar.

        Thread-safe: may be called from background threads.
        """

        self.run_on_ui_thread(lambda: self._notify_ui(title=title, message=message, duration_ms=duration_ms, app_id=app_id))

    def get_battery_info(self):
        try:
            return get_battery_info()
        except Exception:
            return None

    def get_audio_info(self):
        try:
            return get_audio_info()
        except Exception:
            return None

    def get_wifi_info(self):
        try:
            return get_wifi_info()
        except Exception:
            return None

    def _set_media_session_ui(
        self,
        *,
        title: str = "",
        artist: str = "",
        album: str = "",
        artwork_path: str = "",
        position_ms: int | None = None,
        duration_ms: int | None = None,
        playback_state: str = "playing",
        controls: dict | None = None,
        app_id: str | None = None,
    ) -> MediaSession | None:
        if app_id is None:
            app_id = self.active_app_id or ""
        app_id = str(app_id or "").strip()
        if not app_id:
            return None

        try:
            return self.media_sessions.set_session(
                app_id=app_id,
                title=title,
                artist=artist,
                album=album,
                artwork_path=artwork_path,
                position_ms=position_ms,
                duration_ms=duration_ms,
                playback_state=playback_state,
                controls=controls,
            )
        except Exception:
            log.exception("Desktop media session update failed", extra={"app_id": app_id})
            return None

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
        controls: dict | None = None,
        app_id: str | None = None,
    ) -> None:
        self.run_on_ui_thread(
            lambda: self._set_media_session_ui(
                title=title,
                artist=artist,
                album=album,
                artwork_path=artwork_path,
                position_ms=position_ms,
                duration_ms=duration_ms,
                playback_state=playback_state,
                controls=controls,
                app_id=app_id,
            )
        )

    update_media_session = set_media_session

    def clear_media_session(self, *, app_id: str | None = None) -> None:
        if app_id is None:
            app_id = self.active_app_id or ""
        app_id = str(app_id or "").strip()
        if not app_id:
            return
        self.run_on_ui_thread(lambda: self.media_sessions.clear_session(app_id))

    def get_active_media_session(self) -> MediaSession | None:
        try:
            return self.media_sessions.active_session()
        except Exception:
            return None

    def send_media_command(self, command: str, *, app_id: str | None = None, **payload) -> bool:
        try:
            return bool(self.media_sessions.dispatch_command(command, app_id=app_id, **payload))
        except Exception:
            log.exception("Desktop media command dispatch failed", extra={"app_id": str(app_id or ""), "command": str(command)})
            return False

    def enable_background(self, enabled: bool = True, *, app_id: str | None = None) -> None:
        """Opt the given app into staying alive when not foreground."""

        if app_id is None:
            app_id = self.active_app_id
        if not app_id:
            return
        running = self._running.get(app_id)
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

    def background_tasks_allowed(self) -> bool:
        return True

    def has_unlocked_once(self) -> bool:
        return bool(self._has_unlocked_once)

    # ---------------------------------------------------------
    # App discovery (same mechanism)
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

            # This is the real container the app expects.
            container = QWidget()

            instance = app_class(window=self, container=container)

            sub = self.mdi.addSubWindow(container)
            sub.setAttribute(Qt.WA_DeleteOnClose, True)

            # Title
            sub.setWindowTitle(desc.display_name or app_id)

            # Add to MDI
            container.resize(480, 600)
            container.show()

            # Track the actual subwindow so activation and cleanup work reliably.
            self._running[app_id] = sub
            self._running_instances[app_id] = instance

            # Cleanup tracking on close and refresh taskbar
            def _on_destroy(aid=app_id):
                try:
                    self._running.pop(aid, None)
                except Exception:
                    pass
                try:
                    self._running_instances.pop(aid, None)
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
            self._sync_notification_geometry()
            self._position_control_center()
        except Exception:
            pass
        return super().resizeEvent(event)

    def _sync_notification_geometry(self) -> None:
        try:
            if not hasattr(self, "notifications") or self.notifications is None:
                return
            window_width = int(self.width())
            window_height = int(self.height())
            if window_width <= 0 or window_height <= 0:
                return

            popup_width = max(1, int(window_width * 0.25))
            popup_x = max(0, window_width - popup_width)
            self.notifications.set_geometry(x=popup_x, y=0, width=popup_width)
        except Exception:
            pass

    def is_setup_completed(self) -> bool:
        return bool(getattr(self.config, "setup_completed", False))

    def report_app_crash(self, exc_type, exc, tb) -> None:
        log.exception("App crash reported", exc_info=(exc_type, exc, tb))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    shell = MdiShell()
    # shell.showFullScreen()

    sys.exit(app.exec())
