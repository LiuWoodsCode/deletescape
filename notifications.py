from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from typing import Callable
import json
import os
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QHBoxLayout
from logger import get_logger
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect
import datetime
log = get_logger("notifications")


@dataclass(frozen=True)
class Notification:
    app_id: str
    name: str
    app_icon: str
    title: str
    message: str
    duration_ms: int
    timestamp: str


class NotificationBanner(QFrame):
    ICON_SIZE = 40  # px (adjust as desired)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setVisible(False)

        # Avoid stealing clicks unless we want to dismiss.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Root layout: icon (left) + text (right)
        root = QHBoxLayout()
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(10)
        self.setLayout(root)

        # Icon label (left)
        self._icon = QLabel()
        self._icon.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setVisible(False)  # hidden if no icon is set
        root.addWidget(self._icon, 0, Qt.AlignVCenter)

        # Text layout (right)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self._appid = QLabel("")
        self._appid.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._appid.setWordWrap(True)
        self._appid.setStyleSheet("font-size: 10px; font-weight: 600;")

        self._title = QLabel("")
        self._title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 16px; font-weight: 600;")

        self._message = QLabel("")
        self._message.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._message.setWordWrap(True)

        text_layout.addWidget(self._appid)
        text_layout.addWidget(self._title)
        text_layout.addWidget(self._message)

        # Put text layout into root
        root.addLayout(text_layout, 1)

        self._dark_mode = False
        self._on_click = None
        self._apply_theme(False)

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

    def _apply_theme(self, dark_mode: bool) -> None:
        self._dark_mode = bool(dark_mode)

        if self._dark_mode:
            bg = "#000000"
            fg = "#ffffff"
        else:
            bg = "#ffffff"
            fg = "#000000"

        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 15px;"
        )
    def _apply_theme(self, dark_mode: bool) -> None:
        self._dark_mode = bool(dark_mode)

        # Explicit requirement: black background + white text in dark mode,
        # white background + black text in light mode.
        if self._dark_mode:
            bg = "#000000"
            fg = "#ffffff"
        else:
            bg = "#ffffff"
            fg = "#000000"

        # Single stylesheet so we don't fight Qt palette/theme.
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 15px;"
        )

        self._title.setStyleSheet("font-weight: 600;")

    def set_dark_mode(self, dark_mode: bool) -> None:
        if bool(dark_mode) == self._dark_mode:
            return
        self._apply_theme(bool(dark_mode))

    def set_notification(self, n: Notification) -> None:
        self._title.setText(n.title or "")
        self._appid.setText(n.name or "")
        self._message.setText(n.message or "")
        self.set_icon_pixmap(QPixmap(n.app_icon))
        self._title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._message.setVisible(bool(n.message))

    def set_on_click(self, handler: Callable[[], None] | None) -> None:
        self._on_click = handler

    def mousePressEvent(self, event):
        # Tap to open app (if provided) then dismiss.
        if event.button() == Qt.LeftButton:
            try:
                if self._on_click is not None:
                    self._on_click()
            except Exception:
                pass
            self.setVisible(False)
            event.accept()
            return
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()


class NotificationCenter:
    def __init__(self, *, window, parent: QWidget, banner_height_px: int):
        self._window = window
        self._parent = parent
        self._banner_height_px = int(banner_height_px)

        self._banner = NotificationBanner(parent)
        self._banner.setVisible(False)

        self._queue: list[Notification] = []
        self._active: Notification | None = None
        self._hide_timer = QTimer(self._banner)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_and_maybe_next)

    def set_geometry(self, *, x: int, y: int, width: int) -> None:
        # Full-width banner with small side margins.
        margin = 8
        w = max(1, int(width) - margin * 2)
        h = max(1, self._banner_height_px)
        self._banner.setGeometry(int(x) + margin, int(y) + margin, w, h - margin)

    def _find_app_by_id(self, app_id: str):
            """Return the first app matching app_id, else None."""
            target = str(app_id or "").strip()
            if not target:
                return None
            for a in self._window.get_all_apps():
                if str(getattr(a, "app_id", "")).strip() == target:
                    return a
    
    def name_for_app_id(self, app_id: str | None = None):
        """
        Get a rounded icon for a specific app_id.

        - Looks up the app from window.get_visible_apps()
        - Uses app.icon_path (if present)
        - Falls back to a standard desktop icon
        - Caches by (app_id, size_px)
        """
        key = (str(app_id or "").strip())

        # Find app and build icon
        app = self._find_app_by_id(app_id)
        icon_path = getattr(app, "display_name", None) if app is not None else None
        return icon_path
    
    def icon_for_app_id(self, app_id: str | None = None):
        """
        Get a rounded icon for a specific app_id.

        - Looks up the app from window.get_visible_apps()
        - Uses app.icon_path (if present)
        - Falls back to a standard desktop icon
        - Caches by (app_id, size_px)
        """
        key = (str(app_id or "").strip())

        # Find app and build icon
        app = self._find_app_by_id(app_id)
        icon_path = getattr(app, "icon_path", None) if app is not None else None
        return icon_path
    
    def save_notification(self, n):
        # Load existing history or start a new list
        HISTORY_FILE = Path("./userdata/Data/System/notifications.json")
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []

        # Append the notification as a dict
        history.append(n.__dict__)

        # Save it back
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)

    def notify(self, *, title: str, message: str = "", duration_ms: int = 3500, app_id: str = "") -> None:
        log.debug(
            "Notify requested",
            extra={
                "title": str(title or ""),
                "message_len": len(str(message or "")),
                "duration_ms": int(duration_ms),
                "app_id": str(app_id or ""),
                "banner_visible": bool(self._banner.isVisible()),
                "queue_len": len(self._queue),
            },
        )
        icon = self.icon_for_app_id(app_id)
        name = self.name_for_app_id(app_id)
        n = Notification(
            app_id=str(app_id or ""),
            name=str(name or ""),
            app_icon=str(icon),
            title=str(title or ""),
            message=str(message or ""),
            duration_ms=max(750, int(duration_ms)),
            timestamp=datetime.datetime.now().isoformat(),
        )
        self.save_notification(n)

        # Refresh theme at the time of notification.
        try:
            dark_mode = bool(getattr(getattr(self._window, "config", None), "dark_mode", False))
            self._banner.set_dark_mode(dark_mode)
        except Exception:
            log.exception("Failed to refresh banner theme")
            pass

        if self._banner.isVisible():
            self._queue.append(n)
            log.debug("Notification queued", extra={"queue_len": len(self._queue)})
            return

        self._show(n)

    def _show(self, n: Notification) -> None:
        try:
            self._banner.set_notification(n)
        except Exception:
            log.exception("Failed to set banner notification")
            return

        self._active = n

        def _on_click() -> None:
            log.debug("Notification clicked", extra={"app_id": (n.app_id or "").strip()})
            # Stop the timer so we don't race a timeout.
            try:
                if self._hide_timer.isActive():
                    self._hide_timer.stop()
            except Exception:
                pass

            # Launch app if present.
            try:
                app_id = (n.app_id or "").strip()
                if app_id:
                    launch = getattr(self._window, "launch_app", None)
                    if callable(launch):
                        launch(app_id)
            except Exception:
                log.exception("Failed to launch app from notification", extra={"app_id": (n.app_id or "").strip()})
                pass

            # Hide and advance queue.
            try:
                self._hide_and_maybe_next()
            except Exception:
                pass

        # Always allow tap; if app_id is empty it acts like dismiss.
        try:
            self._banner.set_on_click(_on_click)
        except Exception:
            pass

        try:
            # Ensure we're above other overlays.
            self._banner.raise_()
        except Exception:
            pass

        self._banner.setVisible(True)

        log.debug(
            "Notification shown",
            extra={"app_id": n.app_id, "duration_ms": int(n.duration_ms), "queue_len": len(self._queue)},
        )

        try:
            if self._hide_timer.isActive():
                self._hide_timer.stop()
        except Exception:
            pass

        self._hide_timer.start(n.duration_ms)

    def _hide_and_maybe_next(self) -> None:
        if self._active is not None:
            log.debug(
                "Notification hide",
                extra={"app_id": self._active.app_id, "queue_len": len(self._queue)},
            )
        self._banner.setVisible(False)
        self._active = None

        if not self._queue:
            return

        n = self._queue.pop(0)
        log.debug("Notification dequeue", extra={"app_id": n.app_id, "queue_len": len(self._queue)})
        self._show(n)

    def clear(self) -> None:
        log.debug("Notification clear", extra={"queue_len": len(self._queue), "had_active": self._active is not None})
        self._queue.clear()
        self._active = None
        try:
            self._hide_timer.stop()
        except Exception:
            pass
        try:
            self._banner.set_on_click(None)
        except Exception:
            pass
        self._banner.setVisible(False)

    def set_dark_mode(self, dark_mode: bool) -> None:
        try:
            self._banner.set_dark_mode(bool(dark_mode))
        except Exception:
            pass
