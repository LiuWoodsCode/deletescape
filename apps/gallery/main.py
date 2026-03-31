from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy, 
)
from PySide6.QtCore import QPoint

from photo_picker import get_default_dcim_dir, list_gallery_photos


from logger import get_logger

log = get_logger("gallery")


class App(QObject):
    def __init__(self, window, container: QWidget):
        super().__init__(container)
        self.window = window
        self.container = container

        self._dcim_dir: Path = get_default_dcim_dir()
        self._initial_open: Path | None = None
        try:
            self._dcim_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # If another app requested we open a file, consume the open intent.
        try:
            intent_path = Path(__file__).resolve().parents[2] / "userdata" / "Data" / "Application" / "gallery" / "open_intent.json"
            if intent_path.exists():
                try:
                    data = json.loads(intent_path.read_text(encoding="utf-8"))
                    p = data.get("path")
                    if p:
                        photo = Path(p)
                        if photo.exists():
                            # set DCIM dir to parent so preview can work if photo is outside default
                            self._dcim_dir = photo.parent
                            # will open preview after layout initialized
                            self._initial_open = photo
                except Exception:
                    pass
                try:
                    intent_path.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        self._view: str = "grid"  # grid | preview
        self._preview_path: Path | None = None
        self._preview_pix: QPixmap | None = None

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        self.container.setLayout(self.layout)

        self.container.installEventFilter(self)

        self._render_grid()

        # If an initial open photo was requested, show it.
        try:
            if getattr(self, "_initial_open", None) is not None:
                log.debug("Initial open requested")
                self._open_preview(self._initial_open)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if obj is self.container and event.type() == QEvent.Resize:
            if self._view == "preview":
                self._update_preview_pixmap()
        return False

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_grid(self):
        self._view = "grid"
        self._preview_path = None
        self._preview_pix = None
        self._clear_layout()

        photos = list_gallery_photos(self._dcim_dir)
        if not photos:
            empty = QLabel("No photos found. You can import pictures from a computer or take pictures in the Camera app.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self.layout.addWidget(empty, 1)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.layout.addWidget(scroll, 1)

        host = QWidget()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        host.setLayout(grid)
        scroll.setWidget(host)

        thumb_px = 96
        columns = 3

        row = col = 0
        for photo in photos:
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setText(photo.name)

            pix = QPixmap(str(photo))
            if not pix.isNull():
                pix = pix.scaled(thumb_px, thumb_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                btn.setIcon(QIcon(pix))
                btn.setIconSize(pix.size())

            btn.setFixedSize(thumb_px + 34, thumb_px + 48)
            btn.clicked.connect(lambda _=False, p=photo: self._open_preview(p))

            grid.addWidget(btn, row, col)
            col += 1
            if col >= columns:
                col = 0
                row += 1

    def _open_preview(self, path: Path):
        self._view = "preview"
        self._preview_path = path
        self._preview_pix = QPixmap(str(path))
        self._clear_layout()

        title = QLabel(path.name)
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        self.layout.addWidget(title)

        self.preview_label = _ClickableLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)

        # IMPORTANT: allow the label to be smaller than the pixmap's sizeHint
        self.preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.preview_label.setMinimumSize(0, 0)

        # Avoid forcing the window/container to be at least 200px tall:
        # self.preview_label.setMinimumHeight(200)  # <-- remove or keep very small
        # If you want a minimum, keep it small so it won't fight OS constraints:
        self.preview_label.setMinimumHeight(1)

        self.preview_label.setCursor(Qt.PointingHandCursor)
        self.preview_label.clicked.connect(lambda: self._open_fullscreen())
        self.layout.addWidget(self.preview_label, 1)

        # metadata label below image
        self.meta_label = QLabel()
        self.meta_label.setAlignment(Qt.AlignLeft)
        self.meta_label.setWordWrap(True)
        self.layout.addWidget(self.meta_label)

        back = QPushButton("Back")
        back.clicked.connect(self._render_grid)
        self.layout.addWidget(back)

        self._update_preview_pixmap()

    def _display_path(self, p: Path) -> str:
        try:
            rel = p.relative_to(self._root)
            s = str(rel)
            if s == ".":
                return "/"
            # normalize to forward slashes for display
            return "/" + s.replace("\\", "/")
        except Exception:
            s = str(p).replace("\\", "/")
            return s

    def _update_preview_pixmap(self):
            if self._preview_pix is None or self._preview_pix.isNull():
                if hasattr(self, "preview_label"):
                    self.preview_label.setText("Unable to load image")
                return

            if not hasattr(self, "preview_label"):
                return

            # Use contentsRect so you don't scale into the frame/margins
            rect = self.preview_label.contentsRect()
            target_w = max(1, rect.width())
            target_h = max(1, rect.height())

            # If label hasn't been laid out yet, avoid doing a useless scale
            if target_w <= 1 or target_h <= 1:
                return

            # Optional: prevent upscaling (keeps image crisp + avoids huge memory use)
            if target_w >= self._preview_pix.width() and target_h >= self._preview_pix.height():
                scaled = self._preview_pix
            else:
                scaled = self._preview_pix.scaled(
                    target_w, target_h,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

            self.preview_label.setPixmap(scaled)

            # update metadata (unchanged)
            if self._preview_path is not None:
                try:
                    st = self._preview_path.stat()
                    size_kb = max(1, st.st_size // 1024)
                    dims = f"{self._preview_pix.width()}x{self._preview_pix.height()}"
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    meta = f"Size: {size_kb} KB\nDimensions: {dims}\nModified: {mtime}"
                except Exception:
                    meta = "(metadata unavailable)"
                if hasattr(self, "meta_label"):
                    self.meta_label.setText(meta)

    def _open_fullscreen(self):
        if self._preview_pix is None or self._preview_pix.isNull():
            return
        viewer = FullscreenViewer(self._preview_pix)
        viewer.exec_fullscreen()


class _ClickableLabel(QLabel):
    from PySide6.QtCore import Signal

    clicked = Signal()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()


class FullscreenViewer(QWidget):
    def __init__(self, pix: QPixmap):
        super().__init__(None, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._orig_pix = pix
        self._scale = 1.0
        self._dragging = False
        self._last_pos = QPoint()
        self._pinch_start = None

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.layout.addWidget(self.scroll)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setPixmap(self._orig_pix)
        self.image_label.setBackgroundRole(self.backgroundRole())
        self.image_label.setSizePolicy(self.image_label.sizePolicy())

        self.scroll.setWidget(self.image_label)

        # enable touch events for basic pinch support
        self.setAttribute(Qt.WA_AcceptTouchEvents)

    def exec_fullscreen(self):
        self.showFullScreen()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Escape, Qt.Key_Back):
            self.close()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._last_pos = ev.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self._dragging:
            delta = ev.pos() - self._last_pos
            self._last_pos = ev.pos()
            self.scroll.horizontalScrollBar().setValue(self.scroll.horizontalScrollBar().value() - delta.x())
            self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value() - delta.y())

    def mouseReleaseEvent(self, ev):
        self._dragging = False
        self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, ev):
        # zoom in/out with wheel
        angle = ev.angleDelta().y()
        factor = 1.0 + (0.0015 * angle)
        self._set_scale(self._scale * factor)

    def event(self, ev):
        # basic touch pinch handling
        if ev.type() == QEvent.TouchBegin:
            points = ev.touchPoints()
            if len(points) == 2:
                p0 = points[0].pos()
                p1 = points[1].pos()
                self._pinch_start = (p0 - p1).manhattanLength()
            return True
        if ev.type() == QEvent.TouchUpdate and self._pinch_start is not None:
            points = ev.touchPoints()
            if len(points) == 2:
                p0 = points[0].pos()
                p1 = points[1].pos()
                cur = (p0 - p1).manhattanLength()
                if self._pinch_start > 0:
                    ratio = cur / self._pinch_start
                    self._set_scale(self._scale * ratio)
                    self._pinch_start = cur
            return True
        if ev.type() == QEvent.TouchEnd:
            self._pinch_start = None
            return True
        return super().event(ev)

    def _set_scale(self, scale: float):
        scale = max(0.1, min(8.0, scale))
        self._scale = scale
        w = max(1, int(self._orig_pix.width() * self._scale))
        h = max(1, int(self._orig_pix.height() * self._scale))
        scaled = self._orig_pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
