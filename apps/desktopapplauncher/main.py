from PySide6.QtWidgets import (
    QVBoxLayout,
    QStyle,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)
from PySide6.QtCore import QEvent, QObject, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QFont, QFontMetrics


class App(QObject):
    def __init__(self, window, container):
        super().__init__(container)
        self.window = window
        self.container = container

        # iOS-like layout constants (kept local to this app).
        self._grid_cols = 4
        self._apps_per_page = 20  # 4x5
        self._grid_margin_x = 6
        self._grid_margin_top = 2
        self._grid_spacing_x = 7
        self._grid_spacing_y = 7
        self._label_font_size_pt = 9
        self._icon_px = 24
        self._page_dots_height_px = 18

        self._current_page = 0
        self._page_buttons: list[list[QListWidgetItem]] = []
        self._dot_labels: list = []

        # Simplified: no wallpaper. Use container directly as foreground.
        self._fg = container
        self._fg.installEventFilter(self)

        self._root_layout = QVBoxLayout()
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._fg.setLayout(self._root_layout)

        # Main list widget (scrollable).
        self._list = QListWidget(self._fg)
        self._list.setUniformItemSizes(False)
        self._list.setIconSize(QSize(self._icon_px, self._icon_px))
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        self._root_layout.addWidget(self._list, 1)

        self._rebuild_buttons()
        self._apply_styles()
        self._recompute_button_geometry()

    def _sorted_visible_apps(self):
        # Keep ordering stable between runs.
        apps = list(self.window.get_visible_apps())
        try:
            apps.sort(key=lambda a: (str(a.display_name or '').lower(), str(a.app_id or '')))
        except Exception:
            pass
        return apps

    def _choose_dock_apps(self, visible_apps):
        """Dock removed for now; keep method for compatibility."""
        return []

    def _make_rounded_icon(self, icon_path: str | None, size_px: int) -> QIcon:
        if not icon_path:
            return self.window.style().standardIcon(QStyle.SP_DesktopIcon)
        pix = QPixmap(str(icon_path))
        if pix.isNull():
            return self.window.style().standardIcon(QStyle.SP_DesktopIcon)

        target = QSize(size_px, size_px)
        scaled = pix.scaled(target, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size_px) // 2)
        y = max(0, (scaled.height() - size_px) // 2)
        cropped = scaled.copy(x, y, size_px, size_px)

        out = QPixmap(size_px, size_px)
        out.fill(Qt.transparent)

        radius = max(8.0, float(size_px) * 0.22)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(size_px), float(size_px), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()

        return QIcon(out)

    def _make_app_button(self, app, *, icon_px: int, show_label: bool):
        # Kept for compatibility in case other code expects a 'button'-like
        # object. We no longer use QToolButton in the list UI.
        raise NotImplementedError('QToolButton-based buttons are deprecated; use the QListWidget UI')

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_buttons(self) -> None:
        # Populate the QListWidget with visible apps.
        self._list.clear()
        self._page_buttons = []

        visible_apps = self._sorted_visible_apps()
        items: list[QListWidgetItem] = []
        for app in visible_apps:
            icon = self._make_rounded_icon(getattr(app, 'icon_path', None), self._icon_px)
            item = QListWidgetItem(icon, app.display_name or '')
            item.setData(Qt.UserRole, getattr(app, 'app_id', None))
            self._list.addItem(item)
            items.append(item)

        self._page_buttons.append(items)
        # Launch app on activation (double-click or Enter).
        try:
            self._list.itemActivated.disconnect()
        except Exception:
            pass
        self._list.itemActivated.connect(lambda it: self.window.launch_app(it.data(Qt.UserRole)))

        # Also launch on single click so tapping an entry opens the app.
        try:
            self._list.itemClicked.disconnect()
        except Exception:
            pass
        self._list.itemClicked.connect(lambda it: self.window.launch_app(it.data(Qt.UserRole)))

    def _set_page(self, index: int) -> None:
        # Pagination removed; no-op kept for compatibility.
        return

    def _update_page_dots(self) -> None:
        # No page dots in list UI.
        return

    def _dock_background_color(self) -> QColor:
        """Dock removed for now (kept for compatibility)."""
        return QColor(0, 0, 0, 0)

    def _apply_styles(self) -> None:
        # Transparent background (no wallpaper).
        self._fg.setStyleSheet('background: transparent;')

        label_font = QFont()
        label_font.setPointSize(self._label_font_size_pt)
        self._list.setFont(label_font)
        # Make list text readable over backgrounds (if any).
        self._list.setStyleSheet(
            'QListWidget { background: transparent; border: none; color: rgba(255,255,255,235); } '
            'QListWidget::item:selected { background: rgba(255,255,255,30); }'
        )

    def _recompute_button_geometry(self) -> None:
        # Size list items to match icon + label height.
        w = max(1, int(self._fg.width()))
        usable_w = max(1, w - (self._grid_margin_x * 2))

        font = QFont()
        font.setPointSize(self._label_font_size_pt)
        fm = QFontMetrics(font)
        label_h = max(12, int(fm.height()))
        item_h = max(self._icon_px + 12, self._icon_px + label_h + 8)

        self._list.setIconSize(QSize(self._icon_px, self._icon_px))
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None:
                it.setSizeHint(QSize(usable_w, item_h))

    def _next_page(self) -> None:
        return

    def _prev_page(self) -> None:
        return

    def eventFilter(self, obj, event):
        if obj is self._fg and event.type() == QEvent.Resize:
            self._recompute_button_geometry()
        return False

    def on_wallpaper_changed(self) -> None:
        # Wallpaper removed; styles may still need re-applying.
        try:
            self._apply_styles()
        except Exception:
            pass

    def _render_wallpaper(self) -> None:
        # No wallpaper to render.
        return
