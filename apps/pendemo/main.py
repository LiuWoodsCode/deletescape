from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QTabletEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class DrawingCanvas(QWidget):
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._image = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
        self._image.fill(Qt.white)

        self._drawing = False
        self._last_point = QPointF()
        self._brush_color = QColor("#111111")
        self._base_brush_size = 6
        self._eraser_enabled = False
        self._active_source = "Idle"
        self._tablet_active = False

        self.setMinimumSize(280, 280)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_StaticContents)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self._emit_status(1.0)

    def clear_canvas(self) -> None:
        self._ensure_image(self.size())
        self._image.fill(Qt.white)
        self.update()
        self._active_source = "Idle"
        self._emit_status(1.0)

    def set_brush_color(self, color: QColor) -> None:
        self._brush_color = QColor(color)
        self._eraser_enabled = False
        self.update()

    def set_base_brush_size(self, size: int) -> None:
        self._base_brush_size = max(1, int(size))

    def set_eraser_enabled(self, enabled: bool) -> None:
        self._eraser_enabled = bool(enabled)
        self._emit_status(1.0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        painter.drawImage(QPoint(0, 0), self._image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ensure_image(event.size())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.ignore()
            return
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        self._start_stroke(event.position(), 1.0, "Mouse")
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.ignore()
            return
        if not self._drawing or not (event.buttons() & Qt.LeftButton):
            event.ignore()
            return
        self._continue_stroke(event.position(), 1.0, "Mouse")
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.ignore()
            return
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        if self._drawing:
            self._continue_stroke(event.position(), 1.0, "Mouse")
        self._finish_stroke()
        event.accept()

    def tabletEvent(self, event: QTabletEvent) -> None:
        event_type = event.type()
        pressure = self._clamp_pressure(event.pressure())
        pos = event.position()
        self._tablet_active = event_type != QEvent.Type.TabletRelease

        if event_type == QEvent.Type.TabletPress:
            self._start_stroke(pos, pressure, "Pen")
            event.accept()
            return

        if event_type == QEvent.Type.TabletMove:
            self._continue_stroke(pos, pressure, "Pen")
            event.accept()
            return

        if event_type == QEvent.Type.TabletRelease:
            if self._drawing:
                self._continue_stroke(pos, pressure, "Pen")
            self._finish_stroke()
            self._tablet_active = False
            event.accept()
            return

        event.ignore()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            points = event.points()
            if points:
                self._start_stroke(points[0].position(), 1.0, "Touch")
                return True
        elif event.type() == QEvent.Type.TouchUpdate:
            points = event.points()
            if points and self._drawing:
                self._continue_stroke(points[0].position(), 1.0, "Touch")
                return True
        elif event.type() == QEvent.Type.TouchEnd:
            if self._drawing:
                self._finish_stroke()
                return True
        return super().event(event)

    def export_to(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        return self._image.save(str(path), "PNG")

    def _ensure_image(self, size) -> None:
        width = max(1, int(size.width()))
        height = max(1, int(size.height()))

        if self._image.width() >= width and self._image.height() >= height:
            return

        new_image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        new_image.fill(Qt.white)

        painter = QPainter(new_image)
        painter.drawImage(QPoint(0, 0), self._image)
        painter.end()

        self._image = new_image
        self.update()

    def _start_stroke(self, point: QPointF, pressure: float, source: str) -> None:
        self._ensure_image(self.size())
        self._drawing = True
        self._last_point = QPointF(point)
        self._active_source = source
        self._draw_segment(self._last_point, self._last_point, pressure)
        self._emit_status(pressure)

    def _continue_stroke(self, point: QPointF, pressure: float, source: str) -> None:
        if not self._drawing:
            self._start_stroke(point, pressure, source)
            return

        current = QPointF(point)
        previous = QPointF(self._last_point)
        self._active_source = source
        self._draw_segment(previous, current, pressure)
        self._last_point = current
        self._emit_status(pressure)

    def _finish_stroke(self) -> None:
        self._drawing = False
        self._active_source = "Idle"
        self._emit_status(1.0)

    def _draw_segment(self, start: QPointF, end: QPointF, pressure: float) -> None:
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        color = QColor(Qt.white) if self._eraser_enabled else QColor(self._brush_color)
        width = self._stroke_width(pressure)
        pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()

        radius = int(max(4, width))
        dirty = QRect(
            int(min(start.x(), end.x())) - radius,
            int(min(start.y(), end.y())) - radius,
            int(abs(end.x() - start.x())) + radius * 2,
            int(abs(end.y() - start.y())) + radius * 2,
        )
        self.update(dirty)

    def _stroke_width(self, pressure: float) -> float:
        base = float(self._base_brush_size)
        if self._eraser_enabled:
            return base + 10.0
        return max(1.0, base * (0.35 + (self._clamp_pressure(pressure) * 1.65)))

    def _clamp_pressure(self, pressure: float) -> float:
        try:
            value = float(pressure)
        except Exception:
            value = 1.0
        return max(0.0, min(1.0, value))

    def _emit_status(self, pressure: float) -> None:
        width = self._stroke_width(pressure)
        mode = "Eraser" if self._eraser_enabled else "Brush"
        self.status_changed.emit(
            f"Input: {self._active_source} | Mode: {mode} | Pressure: {self._clamp_pressure(pressure):.2f} | Width: {width:.1f}px"
        )


class ColorChip(QToolButton):
    def __init__(self, color: str, *, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedSize(32, 32)
        self.setStyleSheet(
            "QToolButton {"
            f"background:{self._color.name()};"
            "border:2px solid rgba(0,0,0,0.18);"
            "border-radius:16px;"
            "}"
            "QToolButton:checked { border:3px solid #005fcc; }"
        )

    @property
    def color(self) -> QColor:
        return QColor(self._color)


class App(QWidget):
    def __init__(self, window, container):
        super().__init__(container)
        self.window = window
        self.container = container
        self._last_save_path: Path | None = None

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        container.setLayout(root)
        
        tools = QFrame()
        tools_layout = QVBoxLayout()
        tools_layout.setContentsMargins(10, 10, 10, 10)
        tools_layout.setSpacing(8)
        tools.setLayout(tools_layout)
        root.addWidget(tools)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        color_row.addWidget(QLabel("Colors:"))
        self._color_buttons: list[ColorChip] = []
        for idx, color in enumerate(("#111111", "#d7263d", "#1b998b", "#2d6cdf", "#ff9f1c")):
            button = ColorChip(color)
            button.clicked.connect(lambda checked=False, c=button.color: self._set_color(c))
            self._color_buttons.append(button)
            color_row.addWidget(button)
            if idx == 0:
                button.setChecked(True)
        color_row.addStretch(1)
        tools_layout.addLayout(color_row)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        size_row.addWidget(QLabel("Brush size:"))
        self._size_slider = QSlider(Qt.Horizontal)
        self._size_slider.setRange(1, 24)
        self._size_slider.setValue(6)
        self._size_slider.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self._size_slider, 1)
        self._size_label = QLabel("6 px")
        size_row.addWidget(self._size_label)
        tools_layout.addLayout(size_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._eraser_button = QPushButton("Eraser")
        self._eraser_button.setCheckable(True)
        self._eraser_button.toggled.connect(self._toggle_eraser)
        action_row.addWidget(self._eraser_button)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._clear_canvas)
        action_row.addWidget(clear_button)

        save_button = QPushButton("Save PNG")
        save_button.clicked.connect(self._save_canvas)
        action_row.addWidget(save_button)

        action_row.addStretch(1)
        tools_layout.addLayout(action_row)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        tools_layout.addWidget(self._status_label)

        self._canvas = DrawingCanvas(container)
        self._canvas.status_changed.connect(self._status_label.setText)
        root.addWidget(self._canvas, 1)

        self._on_size_changed(self._size_slider.value())
        self._set_color(QColor("#111111"))

    def _set_color(self, color: QColor) -> None:
        self._canvas.set_brush_color(color)
        if self._eraser_button.isChecked():
            self._eraser_button.setChecked(False)

    def _on_size_changed(self, value: int) -> None:
        self._canvas.set_base_brush_size(value)
        self._size_label.setText(f"{int(value)} px")

    def _toggle_eraser(self, enabled: bool) -> None:
        self._canvas.set_eraser_enabled(enabled)

    def _clear_canvas(self) -> None:
        self._canvas.clear_canvas()

    def _save_canvas(self) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        out_dir = base_dir / "userdata" / "Data" / "pendemo"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"drawing-{timestamp}.png"
        ok = self._canvas.export_to(out_path)
        self._last_save_path = out_path if ok else None
        if ok:
            self._status_label.setText(f"Saved to {out_path}")
            notify = getattr(self.window, "notify", None)
            if callable(notify):
                try:
                    notify(title="Pen Demo", message=f"Saved {out_path.name}", duration_ms=2500, app_id="pendemo")
                except Exception:
                    pass
        else:
            self._status_label.setText("Failed to save drawing")

    def on_quit(self) -> None:
        return
