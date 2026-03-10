from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QToolButton,
    QStyle,
    QLabel,
    QWidget,
    QStackedLayout,
)
from PySide6.QtCore import QEvent, QObject, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QFont, QFontMetrics

from wallpaper import load_pixmap, scale_crop_center


class App(QObject):
    def __init__(self, window, container):
        super().__init__(container)
        self.window = window
        self.container = container

        # iOS-like layout constants (kept local to this app).
        self._grid_cols = 4
        self._apps_per_page = 20  # 4x5
        self._grid_margin_x = 18
        self._grid_margin_top = 18
        self._grid_spacing_x = 12
        self._grid_spacing_y = 14
        self._label_font_size_pt = 9
        self._icon_px = 72
        self._page_dots_height_px = 18

        self._current_page = 0
        self._page_buttons: list[list[QToolButton]] = []
        self._dot_labels: list[QLabel] = []

        self._wallpaper_pix = None
        # Stack the wallpaper behind the UI so it always renders.
        stack = QStackedLayout()
        # Show wallpaper + UI at the same time.
        try:
            stack.setStackingMode(QStackedLayout.StackAll)
        except Exception:
            # If StackAll isn't supported, we'll at least keep the UI visible.
            pass
        container.setLayout(stack)

        self._bg = QLabel(container)
        self._bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._bg.setScaledContents(False)
        self._bg.setAlignment(Qt.AlignCenter)
        stack.addWidget(self._bg)

        self._fg = QWidget(container)
        stack.addWidget(self._fg)

        # Ensure the UI layer is active/visible.
        try:
            stack.setCurrentWidget(self._fg)
        except Exception:
            pass

        self._fg.installEventFilter(self)

        self._root_layout = QVBoxLayout()
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._fg.setLayout(self._root_layout)

        # Pages (grid) area.
        self._pages_host = QWidget(self._fg)
        self._pages_layout = QStackedLayout()
        self._pages_layout.setContentsMargins(0, 0, 0, 0)
        self._pages_layout.setSpacing(0)
        self._pages_host.setLayout(self._pages_layout)
        self._root_layout.addWidget(self._pages_host, 1)

        # Page dots area.
        self._dots_host = QWidget(self._fg)
        self._dots_host.setFixedHeight(self._page_dots_height_px)
        dots_layout = QHBoxLayout()
        dots_layout.setContentsMargins(0, 0, 0, 0)
        dots_layout.setSpacing(8)
        self._dots_host.setLayout(dots_layout)
        dots_layout.addStretch(1)
        self._dots_row = QHBoxLayout()
        self._dots_row.setContentsMargins(0, 0, 0, 0)
        self._dots_row.setSpacing(8)
        dots_layout.addLayout(self._dots_row)
        dots_layout.addStretch(1)
        self._root_layout.addWidget(self._dots_host, 0)

        self._rebuild_buttons()
        self._apply_styles()
        self._recompute_button_geometry()

        self.on_wallpaper_changed()

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

    def _find_app_by_id(self, app_id: str):
            """Return the first visible app matching app_id, else None."""
            target = str(app_id or "").strip()
            if not target:
                return None
            try:
                for a in self.window.get_visible_apps():
                    if str(getattr(a, "app_id", "")).strip() == target:
                        return a
            except Exception:
                pass
            return None
    
    def _make_app_button(self, app, *, icon_px: int, show_label: bool) -> QToolButton:
        btn = QToolButton(self._fg)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if show_label else Qt.ToolButtonIconOnly)
        btn.setText(app.display_name if show_label else '')
        btn.setIconSize(QSize(icon_px, icon_px))
        btn.setAutoRaise(True)

        icon = self._make_rounded_icon(getattr(app, 'icon_path', None), icon_px)
        btn.setIcon(icon)
        btn.clicked.connect(lambda _, n=app.app_id: self.window.launch_app(n))
        return btn

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_buttons(self) -> None:
        # Clear existing pages/dots.
        while self._pages_layout.count():
            w = self._pages_layout.widget(0)
            self._pages_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()

        self._clear_layout(self._dots_row)
        self._dot_labels = []
        self._page_buttons = []

        visible_apps = self._sorted_visible_apps()
        grid_apps = list(visible_apps)

        # Build pages.
        pages = [grid_apps[i:i + self._apps_per_page] for i in range(0, len(grid_apps), self._apps_per_page)]
        if not pages:
            pages = [[]]

        for page_idx, page_apps in enumerate(pages):
            page = QWidget(self._pages_host)
            v = QVBoxLayout()
            v.setContentsMargins(self._grid_margin_x, self._grid_margin_top, self._grid_margin_x, 0)
            v.setSpacing(0)
            page.setLayout(v)

            grid = QGridLayout()
            grid.setHorizontalSpacing(self._grid_spacing_x)
            grid.setVerticalSpacing(self._grid_spacing_y)
            grid.setContentsMargins(0, 0, 0, 0)
            v.addLayout(grid)
            v.addStretch(1)

            buttons: list[QToolButton] = []
            for idx, app in enumerate(page_apps):
                r = idx // self._grid_cols
                c = idx % self._grid_cols
                btn = self._make_app_button(app, icon_px=self._icon_px, show_label=True)
                grid.addWidget(btn, r, c)
                buttons.append(btn)
            self._page_buttons.append(buttons)
            self._pages_layout.addWidget(page)

            # Dot indicator.
            dot = QLabel('\u25CF')
            dot.setAlignment(Qt.AlignCenter)
            dot.setFixedSize(10, 10)
            dot.setProperty('pageIndex', page_idx)
            dot.mousePressEvent = lambda e, i=page_idx: self._set_page(i)  # type: ignore[method-assign]
            self._dots_row.addWidget(dot)
            self._dot_labels.append(dot)

        self._set_page(min(self._current_page, self._pages_layout.count() - 1))

    def _set_page(self, index: int) -> None:
        index = max(0, min(int(index), self._pages_layout.count() - 1))
        self._current_page = index
        try:
            self._pages_layout.setCurrentIndex(index)
        except Exception:
            pass
        self._update_page_dots()

    def _update_page_dots(self) -> None:
        pages = self._pages_layout.count()
        self._dots_host.setVisible(pages > 1)
        for i, dot in enumerate(self._dot_labels):
            dot.setProperty('active', i == self._current_page)
            # Force style refresh.
            dot.style().unpolish(dot)
            dot.style().polish(dot)

    def _dock_background_color(self) -> QColor:
        """Dock removed for now (kept for compatibility)."""
        return QColor(0, 0, 0, 0)

    def _apply_styles(self) -> None:
        # Transparent surfaces over wallpaper.
        self._fg.setStyleSheet('background: transparent;')

        label_font = QFont()
        label_font.setPointSize(self._label_font_size_pt)

        # iOS-like labels: small, centered, white.
        common_btn_css = (
            'QToolButton { '
            'background: transparent; '
            'border: none; '
            'color: rgba(255, 255, 255, 235); '
            'padding: 0px; '
            '}'
            'QToolButton:pressed { '
            'color: rgba(255, 255, 255, 255); '
            '}'
        )
        for buttons in self._page_buttons:
            for btn in buttons:
                btn.setFont(label_font)
                btn.setStyleSheet(common_btn_css)

        # Page dots styling.
        dot_css = (
            'QLabel { color: rgba(255,255,255,120); } '
            'QLabel[active="true"] { color: rgba(255,255,255,235); }'
        )
        for dot in self._dot_labels:
            dot.setStyleSheet(dot_css)
        self._update_page_dots()

    def _recompute_button_geometry(self) -> None:
        # Size buttons to fit a 4-column grid cleanly.
        w = max(1, int(self._fg.width()))
        usable_w = max(1, w - (self._grid_margin_x * 2) - (self._grid_spacing_x * (self._grid_cols - 1)))
        cell_w = max(self._icon_px + 10, usable_w // self._grid_cols)

        font = QFont()
        font.setPointSize(self._label_font_size_pt)
        fm = QFontMetrics(font)
        label_h = max(12, int(fm.height()))
        cell_h = self._icon_px + label_h + 16

        for page_buttons in self._page_buttons:
            for btn in page_buttons:
                btn.setFixedSize(cell_w, cell_h)
                btn.setIconSize(QSize(self._icon_px, self._icon_px))

    def _next_page(self) -> None:
        if self._pages_layout.count() <= 1:
            return
        self._set_page((self._current_page + 1) % self._pages_layout.count())

    def _prev_page(self) -> None:
        if self._pages_layout.count() <= 1:
            return
        self._set_page((self._current_page - 1) % self._pages_layout.count())

    def eventFilter(self, obj, event):
        if obj is self._fg and event.type() == QEvent.Resize:
            self._render_wallpaper()
            self._recompute_button_geometry()
        if obj is self._fg and event.type() == QEvent.Wheel:
            # Simple paging like iOS: scroll to change pages.
            try:
                delta = int(getattr(event, 'angleDelta', lambda: None)().y())
            except Exception:
                delta = 0
            if delta < 0:
                self._next_page()
            elif delta > 0:
                self._prev_page()
            return True
        return False

    def on_wallpaper_changed(self) -> None:
        try:
            path = getattr(getattr(self.window, 'config', None), 'home_wallpaper', '') or ''
            self._wallpaper_pix = load_pixmap(path)
        except Exception:
            self._wallpaper_pix = None
        self._render_wallpaper()
        # Re-apply styles in case dark mode changed.
        try:
            self._apply_styles()
        except Exception:
            pass

    def _render_wallpaper(self) -> None:
        if self._wallpaper_pix is None:
            self._bg.clear()
            return
        try:
            target = self._bg.size()
            if target.width() <= 1 or target.height() <= 1:
                # If bg hasn't been laid out yet, fall back to container size.
                target = self.container.size()
            self._bg.setPixmap(scale_crop_center(self._wallpaper_pix, target))
        except Exception:
            self._bg.clear()
