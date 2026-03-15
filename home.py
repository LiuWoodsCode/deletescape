import json
import sys
import os
import traceback
import time
import gc
import threading
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from battery import get_battery_info
from telephony import get_signal_strength
from location import LocationInfo, get_location_info
from wifi import (
    WifiInfo,
    WifiNetwork,
    WifiProfile,
    get_wifi_info,
    scan_wifi_networks,
    list_wifi_profiles,
    add_wifi_profile,
    delete_wifi_profile,
)

from config import ConfigStore, OSBuildConfigStore, OSConfig, DeviceConfigStore, DeviceConfig
from fs_layout import get_user_data_layout
from app_registry import AppDescriptor, discover_apps, load_app_class, unload_app_modules

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLayout,
    QSizePolicy,
    QSpacerItem,
    QWidget,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QObject, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush, QImage, QPixmap, QIcon

from PySide6.QtWidgets import QGraphicsDropShadowEffect

from buttons import ButtonAction, ButtonBinding, ButtonManager

from photo_picker import request_photo_from_gallery
from wallpaper import load_pixmap, scale_crop_center

from background_tasks import BackgroundTaskManager
from notifications import NotificationCenter


STATUS_BAR_HEIGHT_PX = 24
NOTIFICATION_BANNER_HEIGHT_PX = 73

from logger import PROCESS_START, get_logger
log = get_logger("home")


class _MainThreadDispatcher(QObject):
    _invoke = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        # Ensure queued delivery into the QObject's thread (the Qt UI thread).
        self._invoke.connect(self._run, type=Qt.QueuedConnection)

    def _run(self, fn) -> None:
        try:
            fn()
        except Exception:
            # Never let a dispatched UI action crash the shell.
            log.exception("Main-thread dispatch crashed")


def blur_pixmap(pixmap: QPixmap, *, radius: float = 18.0) -> QPixmap:
    """Blur a QPixmap using a QGraphicsBlurEffect.

    This avoids external dependencies (e.g. Pillow) and works cross-platform.
    """

    try:
        if pixmap is None or pixmap.isNull():
            return pixmap

        w = max(1, int(pixmap.width()))
        h = max(1, int(pixmap.height()))

        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pixmap)
        effect = QGraphicsBlurEffect()
        effect.setBlurRadius(float(radius))
        item.setGraphicsEffect(effect)
        scene.addItem(item)

        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        scene.render(painter, QRectF(0.0, 0.0, float(w), float(h)), QRectF(0.0, 0.0, float(w), float(h)))
        painter.end()

        out = QPixmap.fromImage(img)
        return pixmap if out.isNull() else out
    except Exception:
        return pixmap


@dataclass
class RunningApp:
    app_id: str
    widget: QWidget
    instance: object
    background_enabled: bool = False


class _WifiPollThread(QThread):
    wifi_info_ready = Signal(object)

    def __init__(self, *, interval_ms: int = 3000, parent: QObject | None = None):
        super().__init__(parent)
        self._interval_sec = max(0.5, float(interval_ms) / 1000.0)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                info = get_wifi_info()
            except Exception:
                info = WifiInfo()
            self.wifi_info_ready.emit(info)
            if self._stop_event.wait(self._interval_sec):
                break


class _BatteryPollThread(QThread):
    battery_info_ready = Signal(object, object)

    def __init__(self, *, interval_ms: int = 3000, parent: QObject | None = None):
        super().__init__(parent)
        self._interval_sec = max(0.5, float(interval_ms) / 1000.0)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            percentage: int | None = None
            is_charging: bool | None = None
            try:
                info = get_battery_info()
                percentage = getattr(info, "percentage", None)
                is_charging = getattr(info, "is_charging", None)
            except Exception:
                pass
            self.battery_info_ready.emit(percentage, is_charging)
            if self._stop_event.wait(self._interval_sec):
                break


class StatusBarWidget(QWidget):
    def __init__(self, window: 'Deletescape'):
        super().__init__(window)
        self.window = window

        self.setFixedHeight(STATUS_BAR_HEIGHT_PX)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self.time_label, 1)

        self.cellular_widget = NetworkSignalIconWidget(kind='cellular', parent=self)
        layout.addWidget(self.cellular_widget, 0)

        self.wifi_widget = NetworkSignalIconWidget(kind='wifi', parent=self)
        layout.addWidget(self.wifi_widget, 0)

        self.battery_label = QLabel()
        self.battery_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        layout.addWidget(self.battery_label, 0)
        self.battery_label.setText(self._battery_text_from_percentage(None))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(3000)

        self._wifi_poll_thread = _WifiPollThread(interval_ms=3000, parent=self)
        self._wifi_poll_thread.wifi_info_ready.connect(self._on_wifi_info)

        self._battery_poll_thread = _BatteryPollThread(interval_ms=3000, parent=self)
        self._battery_poll_thread.battery_info_ready.connect(self._on_battery_info)

        self._wifi_poll_thread.start()
        self._battery_poll_thread.start()
        self.destroyed.connect(lambda *_: self._shutdown_poll_threads())

        self._last_battery_percentage: int | None = None
        self._last_battery_is_charging: bool | None = None
        self._warned_low_20 = False
        self._warned_critical_10 = False
        self._update()
    def _update_time(self):
        self.time_label.setText(self.window.format_time(datetime.now()))


    def _battery_text_from_percentage(self, percentage: int | None) -> str:
        if percentage is None:
            return "--%"
        return f"{int(percentage)}%"

    def _maybe_emit_battery_warnings(self, *, percentage: int | None, is_charging: bool | None) -> None:
        if percentage is None:
            return

        pct = int(percentage)
        charging = True if is_charging is True else False

        # If we are charging, don't nag, and allow warnings again on the next discharge cycle.
        if charging:
            self._warned_low_20 = False
            self._warned_critical_10 = False
            return

        # Hysteresis so we don't spam if the percentage bounces around a boundary.
        if pct >= 23:
            self._warned_low_20 = False
        if pct >= 13:
            self._warned_critical_10 = False

        last = self._last_battery_percentage

        crossed_20 = (last is None or last > 20) and pct <= 20
        if crossed_20 and not self._warned_low_20:
            self._warned_low_20 = True
            try:
                self.window.notify(
                    title="Battery low",
                    message=f"{pct}% remaining. Please charge soon.",
                    duration_ms=4500,
                    app_id="system",
                )
            except Exception:
                pass

        crossed_10 = (last is None or last > 10) and pct <= 10
        if crossed_10 and not self._warned_critical_10:
            self._warned_critical_10 = True

            def _show_box(p: int) -> None:
                try:
                    QMessageBox.critical(
                        self.window,
                        "Battery critical",
                        f"Battery is at {p}%.\nCharge now.",
                    )
                except Exception:
                    pass

            # Defer so we don't open a modal directly inside a timer tick.
            try:
                QTimer.singleShot(0, lambda p=pct: _show_box(p))
            except Exception:
                _show_box(pct)

    def _update(self):
        self.time_label.setText(self.window.format_time(datetime.now()))

        theme = 'dark' if bool(getattr(self.window.config, 'dark_mode', False)) else 'light'
        self.cellular_widget.set_theme(theme)
        self.wifi_widget.set_theme(theme)

        try:
            strength = get_signal_strength()
            self.cellular_widget.set_level(int(getattr(strength, "bars", 0) or 0))
        except Exception:
            self.cellular_widget.set_level(0)

    def _on_wifi_info(self, wifi: WifiInfo | dict) -> None:
        try:
            level = 0
            connected = bool(getattr(wifi, "connected", False))
            signal = getattr(wifi, "signal_percent", None)
            if connected:
                if signal is None:
                    level = 1
                else:
                    signal = int(signal)
                    if signal <= 15:
                        level = 1
                    elif signal <= 40:
                        level = 2
                    elif signal <= 70:
                        level = 3
                    else:
                        level = 4
            self.wifi_widget.set_level(level)
        except Exception:
            self.wifi_widget.set_level(0)

    def _on_battery_info(self, percentage: int | None, is_charging: bool | None) -> None:
        self.battery_label.setText(self._battery_text_from_percentage(percentage))
        self._maybe_emit_battery_warnings(percentage=percentage, is_charging=is_charging)

        self._last_battery_percentage = percentage
        self._last_battery_is_charging = is_charging

    def _shutdown_poll_threads(self) -> None:
        wifi_thread = getattr(self, "_wifi_poll_thread", None)
        if wifi_thread is not None:
            try:
                wifi_thread.stop()
                wifi_thread.wait(1500)
            except Exception:
                pass
            self._wifi_poll_thread = None

        battery_thread = getattr(self, "_battery_poll_thread", None)
        if battery_thread is not None:
            try:
                battery_thread.stop()
                battery_thread.wait(1500)
            except Exception:
                pass
            self._battery_poll_thread = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window.open_control_center()
            event.accept()
            return
        super().mousePressEvent(event)


class NetworkSignalIconWidget(QLabel):
    def __init__(self, *, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._kind = str(kind)
        self._level = 0
        self._theme = "light"
        self._icon_size = 16
        self._assets_root = Path(__file__).resolve().parent / "assets" / "icons" / "network"

        self.setFixedSize(22, STATUS_BAR_HEIGHT_PX)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._refresh_icon()

    def set_theme(self, theme: str) -> None:
        theme = "dark" if str(theme or "").strip().lower() == "dark" else "light"
        if theme == self._theme:
            return
        self._theme = theme
        self._refresh_icon()

    def set_level(self, level: int) -> None:
        level = max(0, min(4, int(level)))
        if level == self._level:
            return
        self._level = level
        self._refresh_icon()

    def _icon_path(self) -> Path:
        if self._kind == "cellular":
            return self._assets_root / "cellular" / self._theme / "4bar" / f"{self._level}.svg"
        return self._assets_root / "wifi" / self._theme / f"{self._level}.svg"

    def _refresh_icon(self) -> None:
        path = self._icon_path()
        if not path.exists():
            self.clear()
            return

        icon = QIcon(str(path))
        pix = icon.pixmap(self._icon_size, self._icon_size)
        if pix.isNull():
            self.clear()
            return
        self.setPixmap(pix)

class ControlTile(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)

        self.setObjectName("tile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(92)
        self.setStyleSheet("""
        QFrame#tile {
            background-color: #2b2b2b;
            border-radius: 12px;
            border: 1px solid #3c3c3c;
        }
        QLabel#tileTitle {
            color: white;
            font-size: 14px;
            font-weight: 600;
        }
        QLabel#tileSub {
            color: #b0b0b0;
            font-size: 11px;
        }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("tileTitle")
        self.title_lbl.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("tileSub")
        self.sub_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        lay.addStretch(1)
        lay.addWidget(self.title_lbl)
        if subtitle:
            lay.addWidget(self.sub_lbl)

from datetime import datetime, timezone

class NotificationCard(QFrame):
    def __init__(self, app_id: str, app_name: str, title: str, body: str, timestamp, icon=None, parent=None):
        super().__init__(parent)
        self.setObjectName("notifCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
        QFrame#notifCard {
            background-color: #2b2b2b;
            border-radius: 12px;
            border: 1px solid #3c3c3c;
        }
        QLabel#notifTitle {
            color: white;
            font-size: 14px;
            font-weight: 600;
        }
        QLabel#Sub {
            color: #b0b0b0;
            font-size: 11px;
        }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Icon label (left)
        self._icon = QLabel()
        self._icon.setFixedSize(32, 32)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setVisible(False)  # hidden if no icon is set
        lay.addWidget(self._icon, 0, Qt.AlignVCenter)

        # Text layout (right)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        # Top row layout (App name + time)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        self._appid = QLabel(app_name)
        self._appid.setStyleSheet("font-size: 10px; font-weight: 600;")

        self._time = QLabel()
        self._time.setStyleSheet("color: #b0b0b0; font-size: 10px;")
        self._time.setAlignment(Qt.AlignRight)

        top_row.addWidget(self._appid)
        top_row.addStretch()
        top_row.addWidget(self._time)

        # Insert top row into the text layout ABOVE the title
        text_layout.addLayout(top_row)

        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 16px; font-weight: 600;")

        self._message = QLabel(body)
        self._message.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._message.setWordWrap(True)

        text_layout.addWidget(self._appid)
        text_layout.addWidget(self._title)
        text_layout.addWidget(self._message)

        # Put text layout into root
        lay.addLayout(text_layout, 1)
        try:
            self.set_icon_pixmap(QPixmap(icon))
        except:
            pass

        if timestamp:
            self._time.setText(self._format_time_ago(timestamp))
        else:
            self._time.setText("")


    def _format_time_ago(self, iso_timestamp: str) -> str:
        try:
            ts = datetime.fromisoformat(iso_timestamp)  # already in local tz OR naive local time
            now = datetime.now()                        # PC's local time
            seconds = (now - ts).total_seconds()
            if seconds < 60:
                return "Just now"
            elif seconds < 3600:
                mins = int(seconds // 60)
                return f"{mins}m ago"
            elif seconds < 86400:
                hrs = int(seconds // 3600)
                return f"{hrs}h ago"
            else:
                days = int(seconds // 86400)
                return f"{days}d ago"
        except Exception as e:
            import traceback
            return traceback.format_exc()
            
    def set_icon_pixmap(self, pixmap: QPixmap | None) -> None:
        """Set/clear icon on the left."""
        if not pixmap or pixmap.isNull():
            self._icon.clear()
            self._icon.setVisible(False)
            return

        # Scale nicely to the icon label size
        scaled = pixmap.scaled(
            self._icon.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._icon.setPixmap(scaled)
        self._icon.setVisible(True)
        
class ControlCenterOverlay(QWidget):
    def __init__(self, window: 'Deletescape', parent: QWidget):
        super().__init__(parent)
        self.window = window

        self.setVisible(False)

        # Render a blurred screenshot behind the control center content.
        self._bg_pix: QPixmap | None = None
        self._bg = QLabel(self)
        self._bg.setScaledContents(False)
        self._bg.setAlignment(Qt.AlignCenter)
        self._bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._bg.lower()

        # Let the background label show through.
        try:
            self.setAutoFillBackground(False)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
        except Exception:
            pass

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setLayout(layout)

        # --- Time & Date (top-left) ---
        self.time_label = QLabel("12:00 AM")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.date_label = QLabel("January 1st, 1970")
        self.date_label.setObjectName("dateLabel")
        self.date_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)

        # --- 3 tiles row ---
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(12)

        self.wifi_tile = ControlTile("Wi‑Fi", "FunnySSID")
        self.bt_tile = ControlTile("Bluetooth", "My Car")
        self.cell_tile = ControlTile("Cellular Data", "JCJenson Wireless")

        tiles_row.addWidget(self.wifi_tile)
        tiles_row.addWidget(self.bt_tile)
        tiles_row.addWidget(self.cell_tile)

        layout.addLayout(tiles_row)

        # --- Notifications header ---
        notif_hdr = QLabel("Notifications")
        notif_hdr.setObjectName("sectionHeader")
        notif_hdr.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(notif_hdr)

        # --- Notification card ---
        try:
            with open("./userdata/Data/System/notifications.json", "r", encoding="utf-8") as f:
                notifications = json.load(f)
                
            for notif in notifications:
                appid = notif.get("app_id", "unknown")
                app_name = notif.get("name", "unknown")
                title = notif.get("title", "No Title")

                icon_str = notif.get("app_icon")
                timestamp = notif.get("timestamp")
                icon = Path(icon_str) if icon_str and Path(icon_str).exists() else None

                body = notif.get("message", "")

                notif_card = NotificationCard(appid, app_name, title, body, timestamp, icon)
                layout.addWidget(notif_card)
        except FileNotFoundError:
            pass

        # Push content up (big empty area below like your sketch)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Optional close button (your original had it; mockup didn’t)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.window.close_control_center)
        layout.addWidget(close_btn)

        # --- Styling to match thick rounded borders ---
        self.setStyleSheet("""

            QLabel#timeLabel {
                font-size: 44px;
                font-weight: 500;
                margin: 0px;
                padding: 0px;
            }

            QLabel#dateLabel {
                font-size: 16px;
                margin-top: -6px;
            }

            QLabel#sectionHeader {
                font-size: 18px;
                font-weight: 500;
                margin-top: 4px;
            }

            QLabel#notifTitle {
                font-size: 16px;
                font-weight: 600;
            }

            QLabel#notifBody {
                font-size: 13px;
            }

            QPushButton#closeBtn {
                margin-top: 10px;
                padding: 10px 14px;
            }
        """)

        # --- Timer for time/date updates ---
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self._timer.start(1000)
        self._update_time()

    def set_background_pixmap(self, pixmap: QPixmap | None) -> None:
        self._bg_pix = pixmap
        self._update_background_scaled()

    def _update_background_scaled(self) -> None:
        try:
            self._bg.setGeometry(self.rect())
        except Exception:
            return

        pix = self._bg_pix
        if pix is None or pix.isNull() or self.width() <= 0 or self.height() <= 0:
            try:
                self._bg.clear()
            except Exception:
                pass
            return

        try:
            self._bg.setPixmap(scale_crop_center(pix, self.size()))
        except Exception:
            try:
                self._bg.setPixmap(pix)
            except Exception:
                pass

    def _update_time(self):
        self.time_label.setText(self.window.format_time(datetime.now()))

    def mousePressEvent(self, event):
        # Swallow clicks so the paused app doesn't receive them.
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_background_scaled()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self._update_background_scaled()


class LockScreenOverlay(QWidget):
    def __init__(self, window: 'Deletescape', parent: QWidget):
        super().__init__(parent)
        self.window = window

        self.setVisible(False)

        self._wallpaper_pix = None
        self._bg = QLabel(self)
        self._bg.setScaledContents(False)
        self._bg.setAlignment(Qt.AlignCenter)
        self._bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._bg.lower()

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setLayout(layout)

        layout.addStretch(1)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignCenter)
        time_font = QFont()
        time_font.setPointSize(44)
        time_font.setBold(True)
        self.time_label.setFont(time_font)
        self._apply_text_shadow(self.time_label, blur=18, y_offset=2)
        layout.addWidget(self.time_label)

        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignCenter)
        date_font = QFont()
        date_font.setPointSize(16)
        self.date_label.setFont(date_font)
        self._apply_text_shadow(self.date_label, blur=14, y_offset=2)
        layout.addWidget(self.date_label)

        layout.addWidget(QLabel(""))

        hint = QLabel('Press Home to unlock')
        hint.setAlignment(Qt.AlignCenter)
        self._apply_text_shadow(hint, blur=12, y_offset=2)
        layout.addWidget(hint)

        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time_date)
        self._timer.start(1000)
        self._update_time_date()

    def _apply_text_shadow(self, label: QLabel, *, blur: int, y_offset: int) -> None:
        try:
            effect = QGraphicsDropShadowEffect(label)
            effect.setBlurRadius(float(blur))
            effect.setOffset(0.0, float(y_offset))
            effect.setColor(QColor(0, 0, 0, 200))
            label.setGraphicsEffect(effect)
        except Exception:
            pass

    def _update_time_date(self) -> None:
        now = datetime.now()
        try:
            self.time_label.setText(self.window.format_time(now))
        except Exception:
            self.time_label.setText(now.strftime('%H:%M'))

        try:
            self.date_label.setText(now.strftime('%A, %B %d'))
        except Exception:
            self.date_label.setText('')

    def set_wallpaper_path(self, path: str) -> None:
        self._wallpaper_pix = load_pixmap(path)
        self._render_wallpaper()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg.setGeometry(self.rect())
        self._render_wallpaper()

    def _render_wallpaper(self) -> None:
        if self._wallpaper_pix is None:
            self._bg.clear()
            return
        try:
            self._bg.setPixmap(scale_crop_center(self._wallpaper_pix, self.size()))
        except Exception:
            self._bg.clear()

    def mousePressEvent(self, event):
        # Swallow clicks so the underlying UI doesn't receive them.
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()


class SoftwareHomeBarWidget(QWidget):
    def __init__(self, window: 'Deletescape', parent: QWidget):
        super().__init__(parent)
        self.window = window

        # Keep the bar compact; height is intentionally small to not steal content area.
        self.setFixedHeight(42)

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.setLayout(layout)

        layout.addStretch(1)

        self.home_btn = QPushButton('Home')
        self.home_btn.clicked.connect(self._on_home)
        self.home_btn.setDefault(False)
        self.home_btn.setAutoDefault(False)
        self.home_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
            }
        """)
        layout.addWidget(self.home_btn, 0)

        layout.addStretch(1)

    def _on_home(self) -> None:
        # Match the physical HOME behavior (unlock if locked, else go home).
        try:
            self.window._handle_home_button()
        except Exception:
            # Never let the shell crash from the nav button.
            log.exception("Software home button failed")


class Deletescape(QMainWindow):
    def __init__(self, *, show_lock_screen_on_start: bool = True, full_screen: bool = True):
        super().__init__()

        log.info("Deletescape init")
        self.setWindowTitle("Deletescape UI")
        self.resize(480, 854)
        
        self._config_store = ConfigStore()
        self.osinfo = OSBuildConfigStore().load()
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

        self._running_apps: dict[str, RunningApp] = {}
        self._terminating_apps: dict[str, RunningApp] = {}
        self._boot_webengine_preload_view: QWidget | None = None

        # Root UI stays constant: status bar + app content host.
        self.root = QWidget(self)
        
        self.setCentralWidget(self.root)

        root_layout = QVBoxLayout()
        root_layout.setSizeConstraint(QLayout.SetNoConstraint)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.root.setLayout(root_layout)

        self.status_bar = StatusBarWidget(window=self)
        root_layout.addWidget(self.status_bar)

        self.content_host = QWidget(self.root)
        self._content_stack = QStackedLayout()
        self._content_stack.setContentsMargins(0, 0, 0, 0)
        self._content_stack.setSpacing(0)
        self.content_host.setLayout(self._content_stack)
        root_layout.addWidget(self.content_host)

        self.software_home_bar: QWidget | None = None
        if not bool(getattr(self.device, 'has_hw_home', True)):
            self.software_home_bar = SoftwareHomeBarWidget(window=self, parent=self.root)
            root_layout.addWidget(self.software_home_bar)

        # Overlay rendered inside the main window.
        self.control_center = ControlCenterOverlay(window=self, parent=self.root)
        self.lock_screen = LockScreenOverlay(window=self, parent=self.root)

        # Notification overlay sits below the status bar.
        self.notifications = NotificationCenter(
            window=self,
            parent=self.root,
            banner_height_px=NOTIFICATION_BANNER_HEIGHT_PX,
        )

        # Main-thread dispatcher for thread-safe UI actions.
        self._ui_dispatcher = _MainThreadDispatcher(self)

        # Background scheduler for apps.
        self.background_tasks = BackgroundTaskManager(window=self)

        self._sync_overlay_geometry()
        if full_screen:
            self.showFullScreen()
        # Load available apps from the apps/ folder (folder-based apps)
        self.apps: dict[str, AppDescriptor] = self.load_apps()
        log.info("Apps loaded", extra={"count": len(self.apps)})

        # Autostart background/service apps (does not change foreground app).
        self._autostart_apps()

        # Apply persisted UI preferences after QApplication exists.
        self.apply_theme()
        self.status_bar._update_time()

        # Button abstraction layer (keyboard shortcuts for now).
        self.buttons = ButtonManager(self)
        self.buttons.bind_global(
            ButtonBinding(action=ButtonAction.HOME, sequence=self.buttons.chord("Ctrl+Alt+H")),
            self._handle_home_button,
        )
        self.buttons.bind_global(
            ButtonBinding(action=ButtonAction.POWER, sequence=self.buttons.chord("Ctrl+Alt+P")),
            self._handle_power_button,
        )

        # Note: the Home screen is now an app (apps/home.py). Boot will launch it.

        # Device starts locked by default, but boot may defer displaying the lock screen.
        if show_lock_screen_on_start:
            self.show_startup_lock_screen()
        else:
            self.lock_screen.setVisible(False)
            # If the lock screen is suppressed, treat the device as already unlocked.
            # This keeps UI behavior consistent (e.g., control center) and allows
            # background tasks which are gated on the first unlock.
            self._locked = False
            if not self._has_unlocked_once:
                self._has_unlocked_once = True
                log.info("First unlock (startup)")

        # Apply wallpapers after UI is ready.
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

    # ---------------------------------------------------------
    # Load apps from built-in /apps and userdata/Applications.
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
        if key == 'use_24h_time':
            self.status_bar._update_time()
            if hasattr(self, 'control_center'):
                self.control_center._update_time()
        if key in {'lock_wallpaper', 'home_wallpaper'}:
            self.apply_wallpapers()

    def apply_wallpapers(self) -> None:
        try:
            if hasattr(self, 'lock_screen'):
                self.lock_screen.set_wallpaper_path(getattr(self.config, 'lock_wallpaper', '') or '')
        except Exception:
            log.exception("Failed to apply lock wallpaper")
            pass

        # Notify the active app (e.g., Home) if it wants to update its background.
        self._call_active_app_hook('on_wallpaper_changed')

    def apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return

        log.debug("Apply theme", extra={"dark_mode": bool(getattr(self.config, "dark_mode", False))})

        # Minimal dark palette for readability.
        import os
        from PySide6.QtGui import QGuiApplication, QPalette, QColor
        from PySide6.QtCore import Qt

        app = QGuiApplication.instance()

        # Style selection
        if os.name == "nt":
            app.setStyle("windows11")
        else:
            app.setStyle("fusion")

        # Color scheme
        if not os.name == "nt":
            if self.config.dark_mode:
                app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

                # Custom dark palette
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

            else:
                app.styleHints().setColorScheme(Qt.ColorScheme.Light)
        else:
            if self.config.dark_mode:
                app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
            else:
                app.styleHints().setColorScheme(Qt.ColorScheme.Light)
             
    # Helper to return apps that are not marked hidden
    def get_visible_apps(self):
        return [app for app in self.apps.values() if not app.hidden]

    def get_all_apps(self):
        return [app for app in self.apps.values()]

    def is_setup_completed(self) -> bool:
        return bool(getattr(self.config, "setup_completed", False))

    # New: show the home app (used by apps to return to home)
    def show_home(self):
        if 'home' in self.apps:
            self.launch_app('home')

    # ---------------------------------------------------------
    # App API: notifications + background tasks
    # ---------------------------------------------------------
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
            self.notifications.notify(
                title=title,
                message=message,
                duration_ms=duration_ms,
                app_id=str(app_id),
            )
        except Exception:
            log.exception("Notification dispatch failed")

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
    # App API: request a photo from the Gallery (userdata/User/DCIM)
    # ---------------------------------------------------------
    def request_photo(self, *, title: str = "Select Photo", instruction: str = "Pick a photo") -> str | None:
        """Prompt the user to choose a photo from the Gallery.

        Returns the absolute/relative filesystem path to the chosen image, or None if cancelled.
        """

        dcim_dir = get_user_data_layout(Path(__file__).resolve().parent).user_dcim
        return request_photo_from_gallery(self, dcim_dir=dcim_dir, title=title, instruction=instruction)

    # ---------------------------------------------------------
    # App API: location / GPS
    # ---------------------------------------------------------
    def get_location_info(self) -> LocationInfo:
        """Return best-effort current GPS/location information for apps.

        This is safe for apps to call directly as `self.window.get_location_info()`.
        """

        try:
            return get_location_info()
        except Exception:
            return LocationInfo()

    def get_wifi_info(self) -> WifiInfo:
        """Return best-effort Wi-Fi adapter/connection information for apps."""

        try:
            return get_wifi_info()
        except Exception:
            return WifiInfo()

    def scan_wifi_networks(self) -> list[WifiNetwork]:
        """Return best-effort nearby Wi-Fi scan results for apps."""

        try:
            return scan_wifi_networks()
        except Exception:
            return []

    def list_wifi_profiles(self) -> list[WifiProfile]:
        """Return saved Wi-Fi profiles from the active Wi-Fi driver."""

        try:
            return list_wifi_profiles()
        except Exception:
            return []

    def add_wifi_profile(self, ssid: str, *, password: str | None = None, secure: bool | None = None) -> bool:
        """Add a Wi-Fi profile through the active Wi-Fi driver."""

        try:
            return bool(add_wifi_profile(ssid, password=password, secure=secure))
        except Exception:
            return False

    def delete_wifi_profile(self, ssid: str) -> bool:
        """Delete a Wi-Fi profile through the active Wi-Fi driver."""

        try:
            return bool(delete_wifi_profile(ssid))
        except Exception:
            return False

    def _call_active_app_hook(self, hook_name: str) -> None:
        if self.active_app is None:
            return
        hook = getattr(self.active_app, hook_name, None)
        if callable(hook):
            try:
                hook()
            except Exception:
                # App-level hook failures shouldn't crash the OS shell.
                log.exception(
                    "Active app hook failed",
                    extra={"hook": str(hook_name), "active_app_id": str(self.active_app_id or "")},
                )

    def quit_active_app(self) -> None:
        if not self.active_app_id:
            return
        self._terminate_app(self.active_app_id)

    def go_home(self) -> None:
        # Global "Home" button: quit current app and return to home screen.
        if self._control_center_open:
            self.close_control_center()
        if self.active_app_id == 'home':
            log.info("Home button pressed but home is active, so do nothing")
            return
        self.launch_app('home')

    def _terminate_app(self, app_id: str) -> None:
        log.info("Terminate app", extra={"app_id": str(app_id)})
        if app_id in self._terminating_apps:
            log.debug("Terminate app: already terminating", extra={"app_id": str(app_id)})
            return

        running = self._running_apps.pop(app_id, None)
        if running is None:
            log.debug("Terminate app: not running", extra={"app_id": str(app_id)})
            return

        self._terminating_apps[app_id] = running

        try:
            hook = getattr(running.instance, 'on_quit', None)
            if callable(hook):
                hook()
        except Exception:
            log.exception("App on_quit hook failed", extra={"app_id": str(app_id)})
            pass

        try:
            self.background_tasks.cancel_for_app(app_id)
        except Exception:
            log.exception("Failed to cancel tasks for app", extra={"app_id": str(app_id)})
            pass

        try:
            running.widget.hide()
            running.widget.setEnabled(False)
            running.widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass

        try:
            idx = self._content_stack.indexOf(running.widget)
            if idx >= 0:
                self._content_stack.removeWidget(running.widget)
        except Exception:
            pass

        if self.active_app_id == app_id:
            self.active_app = None
            self.active_app_id = None
            log.debug("Active app cleared", extra={"app_id": str(app_id)})

        try:
            if not bool(running.widget.property("_deletescapeTerminateHookInstalled")):
                running.widget.setProperty("_deletescapeTerminateHookInstalled", True)
                running.widget.destroyed.connect(
                    lambda *_args, app_id=app_id: QTimer.singleShot(
                        0, lambda app_id=app_id: self._finalize_terminated_app(app_id)
                    )
                )
        except Exception:
            log.exception("Failed to install teardown hook", extra={"app_id": str(app_id)})

        QTimer.singleShot(0, lambda app_id=app_id: self._dispose_terminating_widget(app_id))

    def _dispose_terminating_widget(self, app_id: str) -> None:
        running = self._terminating_apps.get(app_id)
        if running is None:
            return

        try:
            running.widget.setParent(None)
            running.widget.deleteLater()
        except Exception:
            log.exception("Failed to dispose terminating app widget", extra={"app_id": str(app_id)})
            self._finalize_terminated_app(app_id)

    def _finalize_terminated_app(self, app_id: str) -> None:
        running = self._terminating_apps.pop(app_id, None)
        if running is None:
            return

        # Unload the app only after Qt has torn down the widget tree so PySide
        # does not have to resolve wrappers from a module we just dropped.
        try:
            desc = self.apps.get(app_id)
            if desc is not None:
                removed = unload_app_modules(desc)
                log.debug("Unloaded app modules", extra={"app_id": str(app_id), "removed": int(removed)})
        except Exception:
            log.exception("Failed to unload app modules", extra={"app_id": str(app_id)})

        try:
            gc.collect()
        except Exception:
            pass

    def _call_app_hook(self, app_id: str, hook_name: str) -> None:
        running = self._running_apps.get(app_id)
        if running is None:
            return
        hook = getattr(running.instance, hook_name, None)
        if callable(hook):
            try:
                hook()
            except Exception:
                log.exception("App hook failed", extra={"app_id": str(app_id), "hook": str(hook_name)})
                # Hook failures are treated as a crash for the foreground app.
                if self.active_app_id == app_id:
                    self.report_app_crash(*sys.exc_info())

    def _get_or_start_app(self, app_id: str) -> RunningApp | None:
        if app_id in self._running_apps:
            log.debug("App already running", extra={"app_id": str(app_id)})
            return self._running_apps[app_id]

        if app_id not in self.apps:
            log.warning("Unknown app id", extra={"app_id": str(app_id)})
            return None

        desc = self.apps[app_id]
        app_class = desc.app_class
        if app_class is None:
            try:
                app_class = load_app_class(desc)
                desc.app_class = app_class
            except Exception:
                log.exception("Failed to load app class", extra={"app_id": str(app_id)})
                app_class = None

        if app_class is None:
            log.warning("Cannot start app (no App class)", extra={"app_id": str(app_id)})
            return None

        app_widget = QWidget(self.content_host)
        self._content_stack.addWidget(app_widget)

        log.info("Instantiate app", extra={"app_id": str(app_id), "class": getattr(app_class, "__name__", str(app_class))})

        try:
            instance = app_class(window=self, container=app_widget)
        except Exception:
            log.exception("App constructor failed", extra={"app_id": str(app_id)})
            # Remove the widget we just added.
            try:
                self._content_stack.removeWidget(app_widget)
                app_widget.setParent(None)
                app_widget.deleteLater()
            except Exception:
                pass
            self.report_app_crash(*sys.exc_info())
            return None

        # Helpful convention: give the instance its stable app id.
        try:
            setattr(instance, 'app_id', app_id)
        except Exception:
            pass

        running = RunningApp(app_id=app_id, widget=app_widget, instance=instance)
        self._running_apps[app_id] = running
        log.debug("App started", extra={"app_id": str(app_id)})
        return running

    def _set_app_paused(self, paused: bool):
        # Disable UI interaction for the app area.
        self.content_host.setEnabled(not paused)

        # Optional hooks for apps that manage timers/threads.
        if self.active_app is None:
            return
        hook_name = 'on_pause' if paused else 'on_resume'
        hook = getattr(self.active_app, hook_name, None)
        if callable(hook):
            try:
                hook()
            except Exception:
                # Treat pause/resume hook failures as an app crash, not an OS crash.
                self.report_app_crash(*sys.exc_info())

    def _extract_tb_frames(self, tb):
        import traceback
        frames = []

        for frame in traceback.extract_tb(tb):
            frames.append({
                "filename": frame.filename,
                "lineno": frame.lineno,
                "name": frame.name,
                "line": frame.line
            })

        return frames
    
    def _walk_tb_with_locals(self, tb):
        frames = []

        while tb:
            f = tb.tb_frame
            frames.append({
                "filename": f.f_code.co_filename,
                "function": f.f_code.co_name,
                "lineno": tb.tb_lineno,
                
                "locals": {
                    k: repr(v)
                    for k, v in f.f_locals.items()
                }
            })
            tb = tb.tb_next

        return frames
    
    def _safe_repr(self, obj, maxlen=2048):
        try:
            r = repr(obj)
            if len(r) > maxlen:
                return r[:maxlen] + "...<truncated>"
            return r
        except Exception as e:
            return f"<repr-error {type(e).__name__}>"
        
    def _inspect_frame_deep(self, frame, lineno):
        import dis
        import inspect
        import sys
        import gc
        import traceback

        code = frame.f_code

        try:
            instructions = list(dis.get_instructions(code))
            lasti = frame.f_lasti

            current_instr = None
            for i in instructions:
                if i.offset == lasti:
                    current_instr = {
                        "opname": i.opname,
                        "arg": i.arg,
                        "argval": self._safe_repr(i.argval),
                        "argrepr": i.argrepr,
                        "offset": i.offset
                    }
                    break
        except Exception:
            current_instr = None

        try:
            disassembly = dis.Bytecode(code).dis()
        except Exception:
            disassembly = "<disassembly-failed>"

        try:
            closure = inspect.getclosurevars(frame)
            closure_data = {
                "nonlocals": {k:self._safe_repr(v) for k,v in closure.nonlocals.items()},
                "globals": {k:self._safe_repr(v) for k,v in closure.globals.items()},
                "builtins": list(closure.builtins.keys()),
                "unbound": list(closure.unbound)
            }
        except Exception:
            closure_data = None

        try:
            generator_state = inspect.getgeneratorstate(frame) \
                if inspect.isgenerator(frame) else None
        except Exception:
            generator_state = None

        return {
            "filename": code.co_filename,
            "function": code.co_name,
            "lineno": lineno,
            "lasti": frame.f_lasti,
            "current_instruction": current_instr,

            "locals": {k:self._safe_repr(v) for k,v in frame.f_locals.items()},
            "globals": list(frame.f_globals.keys())[:200],

            "code": {
                "argcount": code.co_argcount,
                "kwonlyargcount": code.co_kwonlyargcount,
                "nlocals": code.co_nlocals,
                "stacksize": code.co_stacksize,
                "flags": code.co_flags,
                "names": code.co_names,
                "varnames": code.co_varnames,
                "freevars": code.co_freevars,
                "cellvars": code.co_cellvars,
                "consts": [self._safe_repr(c) for c in code.co_consts],
            },

            "closure": closure_data,
            "generator_state": generator_state,
            "stack_snapshot": traceback.format_stack(frame),

            "memory": {
                "frame_size": sys.getsizeof(frame),
                "locals_size": sys.getsizeof(frame.f_locals)
            },

            "referrers": len(gc.get_referrers(frame)),

            "disassembly": disassembly,
        }
        
    def _exception_chain(self, exc):
        chain = []
        cur = exc

        while cur:
            chain.append({
                "type": type(cur).__name__,
                "message": str(cur),
                "repr": self._safe_repr(cur)
            })
            cur = cur.__cause__ or cur.__context__

        return chain
    
    def _thread_dump(self):
        import sys
        import threading
        import traceback

        dump = {}

        for tid, frame in sys._current_frames().items():
            dump[str(tid)] = {
                "thread": threading._active.get(tid).name
                    if tid in threading._active else "unknown",
                "stack": traceback.format_stack(frame)
            }

        return dump
    
    def _build_app_panic_report(self, exc_type, exc, tb, app_id, app_name):
        import sys
        import threading
        import platform
        import traceback
        import inspect
        from datetime import datetime
        dev_cfg = DeviceConfigStore().load()
        try:
            report = {
                "timestamp": datetime.now().isoformat(),

                "app": {
                    "id": str(app_id),
                    "name": str(app_name),
                    "active_app_id": str(self.active_app_id),
                    "loaded_apps": list(self.apps.keys()),
                },

                "exception": {
                    "type": exc_type.__name__,
                    "message": str(exc),
                    "repr": self._safe_repr(exc),
                    "chain": self._exception_chain(exc),
                },

                "traceback": {
                    "frames": self._walk_tb_with_locals(tb),
                    "formatted": traceback.format_exception(exc_type, exc, tb)
                },

                "runtime": {
                    "thread": threading.current_thread().name,
                    "thread_id": threading.get_ident(),

                    "python": {
                        "version": sys.version,
                        "build": platform.python_build(),
                        "compiler": platform.python_compiler(),
                        "implementation": platform.python_implementation(),
                    },
                    
                    "system": {
                        "hostos": {
                            "system": platform.system(),
                            "release": platform.release(),
                            "version": platform.version(),
                            "machine": platform.machine(),
                            "processor": platform.processor(),
                            "kernel": platform.uname(),
                        },
                        "device": {
                            "vendor": dev_cfg.manufacturer,
                            "model": dev_cfg.model,
                            "display_name": dev_cfg.model_name,
                            "hw_rev": dev_cfg.hardware_revision,
                            "hostname": platform.node(),
                        },
                        "deletescape": {
                            "display_name": self.osinfo.os_name,
                            "build_id": self.osinfo.build_id,
                            "channel": self.osinfo.channel,
                            "builder": {
                                "hostname": self.osinfo.builder_hostname,
                                "username": self.osinfo.builder_username,
                                "datetime": self.osinfo.build_datetime,
                            }
                        }
                    },

                    "argv": sys.argv,
                    "cwd": getattr(__import__("os"), "getcwd")(),
                },

                "threads": self._thread_dump(),
            }

            return report

        except Exception as panic_exc:
            log.warning("Error while saving panic, trying again with less detail")
            try:
                output = {
                "timestamp": datetime.now().isoformat(),
                "app": {
                    "id": str(app_id),
                    "name": str(app_name),
                },
                "exception": {
                    "type": exc_type.__name__,
                    "message": str(exc),
                    "repr": repr(exc),
                    "cause": repr(exc.__cause__) if exc.__cause__ else None,
                    "context": repr(exc.__context__) if exc.__context__ else None,
                    "frames": self._walk_tb_with_locals(tb),
                },
                "runtime": {
                    "active_app_id": str(self.active_app_id),
                    "loaded_apps": list(self.apps.keys()),
                    "thread": threading.current_thread().name,
                    "python": sys.version,
                    "platform": platform.platform(),
                    "argv": sys.argv,
                }
            }
            except Exception: 
                log.warning("Error while saving panic, trying again with no frames")
                try:
                    output = {
                    "timestamp": datetime.now().isoformat(),
                    "app": {
                        "id": str(app_id),
                        "name": str(app_name),
                    },
                    "exception": {
                        "type": exc_type.__name__,
                        "message": str(exc),
                        "repr": repr(exc),
                        "cause": repr(exc.__cause__) if exc.__cause__ else None,
                        "context": repr(exc.__context__) if exc.__context__ else None,
                        "frames": self._extract_tb_frames(tb),
                    },
                    "runtime": {
                        "active_app_id": str(self.active_app_id),
                        "loaded_apps": list(self.apps.keys()),
                        "thread": threading.current_thread().name,
                        "python": sys.version,
                        "platform": platform.platform(),
                        "argv": sys.argv,
                    }
                }
                except Exception as e:
                    raise e
        return output
                    

    def report_app_crash(self, exc_type, exc, tb) -> None:
        """Show a crash message and recover back to the Home app."""
        if self._handling_crash:
            return
        self._handling_crash = True

        log.exception(
            "Whoops! App crash reported",
            exc_info=(exc_type, exc, tb),
            extra={"active_app_id": str(self.active_app_id or "")},
        )

        crashed_app_id = self.active_app_id
        crashed_name = crashed_app_id or "Unable to get the crashed app name. This is yet another kludge, as an app should not have a name this long. #freetillie"
        try:
            if crashed_app_id in self.apps:
                crashed_name = self.apps[crashed_app_id].display_name or crashed_app_id
        except Exception:
            pass

        try:
            try:
                traceback.print_exception(exc_type, exc, tb)
                exception = traceback.format_tb(exc_type, exc, tb)
            except Exception:
                pass

            try:
                panic = self._build_app_panic_report(
                    exc_type,
                    exc,
                    tb,
                    crashed_app_id,
                    crashed_name
                )

                from pathlib import Path
                import json
                from datetime import datetime

                log_dir = Path("./logs")
                log_dir.mkdir(parents=True, exist_ok=True)

                ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
                fname = log_dir / f"{crashed_app_id}_{ts}.json"

                tmp = fname.with_suffix(".tmp")

                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(panic, f, indent=2)

                tmp.replace(fname)

            except Exception:
                log.exception("Failed to write app panic report. Whoops!")

            try:
                if crashed_name == "Unable to get the crashed app name. This is yet another kludge, as an app should not have a name this long. #freetillie":

                    # if we are given this klduge as the app name, assume pre-init
                    # this often arrises from some issue in an app
                    # causing deletescape to not find it's App() class
                    # but this can happen in weird edge cases
                    # at least it's better than null
                    QMessageBox.critical(
                        self,
                        "We couldn't launch this app",
                        f"{crashed_app_id if crashed_app_id is not None else 'Project Deletescape'} experienced an issue{" and couldn't launch the app" if crashed_app_id is None else ""}. Try again later.",
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "App crashed",
                        f"{crashed_name} (id: {crashed_app_id if crashed_app_id is not None else ''}) experienced an error and had to be closed.\nA crash dump was saved to {fname}",
                    )
            except Exception:
                # something is very wrong
                raise Exception
                
            # Close overlay if open so Home is usable.
            try:
                if self._control_center_open:
                    self.close_control_center()
            except Exception:
                pass

            # Tear down the crashed app UI and attempt to relaunch Home.
            try:
                if crashed_app_id:
                    self._terminate_app(crashed_app_id)
                else:
                    self.quit_active_app()
            except Exception:
                try:
                    self.active_app = None
                    self.active_app_id = None
                except Exception:
                    pass

            try:
                if 'home' in self.apps:
                    self.launch_app('home')
            except Exception:
                # If Home itself fails, leave the shell running with status bar.
                try:
                    self.active_app = None
                    self.active_app_id = None
                except Exception:
                    pass
        finally:
            self._handling_crash = False

    def _sync_overlay_geometry(self):
        if not hasattr(self, 'control_center'):
            return
        # Cover the full window area inside the main window.
        self.control_center.setGeometry(self.root.rect())
        if hasattr(self, 'lock_screen'):
            self.lock_screen.setGeometry(self.root.rect())

        try:
            r = self.root.rect()
            self.notifications.set_geometry(
                x=r.x(),
                y=r.y() + STATUS_BAR_HEIGHT_PX,
                width=r.width(),
            )
        except Exception:
            pass

        self._sync_overlay_z_order()

    def _sync_overlay_z_order(self) -> None:
        """Ensure overlays stack correctly.

        Priority:
        - Lock screen on top, but keep software Home above it (so you can unlock).
        - Control center on top of normal UI (and above the software Home bar).
        - Otherwise, software Home bar above app content.
        """

        # Lock screen visible: lock screen, then home bar above it.
        try:
            if hasattr(self, 'lock_screen') and self.lock_screen.isVisible():
                self.lock_screen.raise_()
                try:
                    if self.software_home_bar is not None:
                        self.software_home_bar.raise_()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Control center visible: keep it above the home bar.
        try:
            if hasattr(self, 'control_center') and self.control_center.isVisible():
                self.control_center.raise_()
                return
        except Exception:
            pass

        # Default: home bar above app content.
        try:
            if self.software_home_bar is not None:
                self.software_home_bar.raise_()
        except Exception:
            pass

    def _show_lock_overlay(self, visible: bool) -> None:
        if not hasattr(self, 'lock_screen'):
            return
        self._sync_overlay_geometry()
        self.lock_screen.setVisible(visible)
        self._sync_overlay_z_order()

    def is_locked(self) -> bool:
        return self._locked

    def lock_device(self) -> None:
        if self._locked:
            return
        log.info("Lock device")
        if self._control_center_open:
            self.close_control_center()
        self._locked = True
        self._set_app_paused(True)
        self._show_lock_overlay(True)

    def unlock_device(self) -> None:
        if not self._locked:
            return
        log.info("Unlock device")
        self._locked = False
        if not self._has_unlocked_once:
            self._has_unlocked_once = True
            log.info("First unlock")
        self._show_lock_overlay(False)
        self._set_app_paused(False)
        if self.active_app_id is None and 'home' in self.apps:
            self.launch_app('home')

    def has_unlocked_once(self) -> bool:
        return bool(self._has_unlocked_once)

    def _handle_home_button(self) -> None:
        log.debug("HOME button")
        if self._locked:
            self.unlock_device()
            return
        self.go_home()

    def _handle_power_button(self) -> None:
        log.debug("POWER button")
        # Requirement: once unlocked, allow entering locked state via POWER.
        if self._locked:
            return
        self.lock_device()

    def open_control_center(self):
        if self._locked:
            return
        if self._control_center_open:
            return
        log.info("Open control center")
        self._control_center_open = True

        self._sync_overlay_geometry()
        # Capture the current UI (behind the overlay), blur it, and use it as the background.
        try:
            QApplication.processEvents()
            shot = self.root.grab()
            self.control_center.set_background_pixmap(blur_pixmap(shot, radius=22.0))
        except Exception:
            log.exception("Failed to capture blurred control center background")

        self._set_app_paused(True)
        self.control_center.setVisible(True)
        self._sync_overlay_z_order()

    def close_control_center(self):
        if not self._control_center_open:
            return
        log.info("Close control center")
        self.control_center.setVisible(False)
        self._set_app_paused(False)
        self._control_center_open = False
        self._sync_overlay_z_order()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_overlay_geometry()

    # ---------------------------------------------------------
    # Launch app and give it the container widget
    # ---------------------------------------------------------
    def launch_app(self, name):
        if self._locked:
            log.warning("Attempting to open app while locked, ignoring...", extra={"app_id": str(name), "prev_app_id": str(self.active_app_id or "")})
            return

        if name == 'home' and not self.is_setup_completed() and 'setupwizard' in self.apps:
            log.warning("Attempting to go home during setup, going to setup instead...", extra={"app_id": str(name), "prev_app_id": str(self.active_app_id or "")})
            name = 'setupwizard'

        # Guard: ignore requests for unknown apps
        if name not in self.apps:
            log.warning("App does not exist, ignoring", extra={"app_id": str(name), "prev_app_id": str(self.active_app_id or "")})
            return

        log.info("Launch app", extra={"app_id": str(name), "prev_app_id": str(self.active_app_id or "")})

        prev_id = self.active_app_id
        prev_to_terminate: str | None = None
        if prev_id and prev_id != name:
            # Allow apps to react to backgrounding.
            self._call_app_hook(prev_id, 'on_pause')

            # If the app didn't opt into background, terminate it.
            prev_running = self._running_apps.get(prev_id)
            if prev_running is not None and not prev_running.background_enabled:
                log.debug(
                    "Previous app not background-enabled; terminating",
                    extra={"prev_app_id": str(prev_id)},
                )
                prev_to_terminate = prev_id

        running = self._get_or_start_app(name)
        if running is None:
            return

        self.active_app_id = name
        self.active_app = running.instance

        try:
            self._content_stack.setCurrentWidget(running.widget)
        except Exception:
            pass

        if prev_to_terminate:
            QTimer.singleShot(0, lambda app_id=prev_to_terminate: self._terminate_app(app_id))

        # Foreground hook.
        self._call_app_hook(name, 'on_resume')
        log.debug("App in foreground", extra={"app_id": str(name)})
