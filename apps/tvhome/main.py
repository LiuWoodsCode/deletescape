from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QSizePolicy,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QToolButton,
    QStyle,
    QLabel,
    QWidget,
    QStackedLayout,
    QDialog,
)
from PySide6.QtCore import QEvent, QObject, Qt, QSize, QTimer, QDateTime
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QFont, QFontMetrics

from wallpaper import load_pixmap, scale_crop_center


class App(QObject):
    def __init__(self, window, container):
        super().__init__(container)
        self.window = window
        self.container = container

        # iOS-like layout constants (kept local to this app).
        self._max_grid_rows = None   # <- your hard limit
        self._max_grid_cols = None
        self._grid_cols = 4
        self._apps_per_page = 20
        self._grid_margin_x = 18
        self._grid_margin_top = 18
        self._grid_spacing_x = 16
        self._grid_spacing_y = 14
        self._label_font_size_pt = 9
        self._icon_px = 85
        self._page_dots_height_px = 18

        self._current_page = 0
        self._page_selection_indices: list[int] = []
        self._page_buttons: list[list[QToolButton]] = []
        self._dot_labels: list[QLabel] = []
        self._icon_cache: dict[tuple[str, int], QIcon] = {}
        self._wallpaper_render_scheduled = False
        self._selected_app_id: str | None = None
        self._keyboard_activity_timer: QTimer | None = None
        self._keyboard_focus_visible = False

        self._wallpaper_pix = None
        self._time_label: QLabel | None = None
        self._settings_panel: QWidget | None = None
        self._settings_button: QToolButton | None = None
        self._settings_focused = False
        self._time_update_timer: QTimer | None = None
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
        self._bg.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._bg.setMinimumSize(0, 0)
        self._bg.setMaximumSize(16777215, 16777215)
        stack.addWidget(self._bg)

        self._fg = QWidget(container)
        self._fg.setFocusPolicy(Qt.StrongFocus)
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

        # Top bar with time and settings
        self._create_top_bar()

        # Pages (grid) area.
        self._pages_host = QWidget(self._fg)
        self._pages_layout = QStackedLayout()
        self._pages_layout.setContentsMargins(0, 0, 0, 0)
        self._pages_layout.setSpacing(0)
        self._pages_host.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )

        self._pages_host.setMinimumSize(0, 0)
        self._pages_host.setMaximumSize(16777215, 16777215)

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

        self._recompute_grid_capacity()
        self._apply_styles()
        # self._recompute_button_geometry()

        # Start time update timer
        self._start_time_update_timer()

        self.on_wallpaper_changed()

    def _recompute_grid_capacity(self):
        rect = self._pages_host.contentsRect()

        if rect.width() <= 0 or rect.height() <= 0:
            return

        # --- Measure label height dynamically ---
        font = QFont()
        font.setPointSize(self._label_font_size_pt)
        fm = QFontMetrics(font)
        label_h = fm.height()

        cell_w = self._icon_px + 10 + self._grid_spacing_x
        cell_h = self._icon_px + label_h + self._grid_spacing_y

        avail_w = rect.width() - (self._grid_margin_x * 2)
        avail_h = rect.height() - self._grid_margin_top

        cols = max(1, avail_w // cell_w)
        rows = max(1, avail_h // cell_h)

        # Apply max row limit
        if self._max_grid_rows is not None:
            rows = min(rows, self._max_grid_rows)

        # Apply max row limit
        if self._max_grid_cols is not None:
            cols = min(cols, self._max_grid_cols)

        new_capacity = int(cols * rows)

        # Only rebuild if layout actually changes
        if cols != self._grid_cols or new_capacity != self._apps_per_page:
            self._grid_cols = int(cols)
            self._apps_per_page = new_capacity
            self._rebuild_buttons()
            self._apply_styles()
            self._render_wallpaper()

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
        cache_key = (str(icon_path or ''), int(size_px))
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached

        if not icon_path:
            icon = self.window.style().standardIcon(QStyle.SP_DesktopIcon)
            self._icon_cache[cache_key] = icon
            return icon

        pix = QPixmap(str(icon_path))
        if pix.isNull():
            icon = self.window.style().standardIcon(QStyle.SP_DesktopIcon)
            self._icon_cache[cache_key] = icon
            return icon

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

        icon = QIcon(out)
        self._icon_cache[cache_key] = icon
        return icon

    def _find_app_by_id(self, app_id: str):
            """Return the first visible app matching app_id, else None."""
            target = str(app_id or "").strip()
            if not target:
                return None
            try:
                for a in self.window.get_all_apps():
                    if str(getattr(a, "app_id", "")).strip() == target:
                        return a
            except Exception:
                pass
            return None
    
    def _make_app_button(self, app, *, icon_px: int, show_label: bool) -> QWidget:
        wrapper = QWidget(self._fg)
        wrapper.setFocusPolicy(Qt.StrongFocus)
        wrapper.installEventFilter(self)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        wrapper.setLayout(lay)

        btn = QToolButton(wrapper)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setIconSize(QSize(icon_px, icon_px))
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setAutoRaise(True)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        icon = self._make_rounded_icon(getattr(app, 'icon_path', None), icon_px)
        btn.setIcon(icon)

        btn.pressed.connect(lambda w=wrapper: w.setFocus())
        btn.clicked.connect(lambda _, n=app.app_id: self.window.launch_app(n))

        lay.addWidget(btn, 0, Qt.AlignHCenter)
        wrapper.setProperty('_btn', btn)

        if show_label:
            lbl = QLabel(app.display_name, wrapper)
            lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

            font = QFont()
            font.setPointSize(self._label_font_size_pt)
            lbl.setFont(font)

            lbl.setWordWrap(False)
            lbl.setFixedWidth(icon_px + 6)     # THIS IS THE MAGIC
            lbl.setMaximumWidth(icon_px + 6)

            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            # iOS‑style two‑line elide
            fm = QFontMetrics(font)
            text = app.display_name
            lines = []

            while text:
                part = fm.elidedText(text, Qt.ElideRight, icon_px + 6)
                lines.append(part)
                text = text[len(part):]
                if len(lines) == 1:
                    break

            lbl.setText("\n".join(lines))

            lay.addWidget(lbl, 0, Qt.AlignHCenter)
            wrapper.setProperty('_lbl', lbl)

        wrapper.setProperty('appId', str(app.app_id))
        wrapper.setProperty('selected', False)
        return wrapper

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
        self._page_selection_indices = []

        visible_apps = self._sorted_visible_apps()
        grid_apps = list(visible_apps)
        selected_app_id = str(self._selected_app_id or '').strip()

        # Build pages.
        pages = [grid_apps[i:i + self._apps_per_page] for i in range(0, len(grid_apps), self._apps_per_page)]
        if not pages:
            pages = [[]]

        for page_idx, page_apps in enumerate(pages):
            page = QWidget(self._pages_host)
            page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            page.setMinimumSize(0, 0)
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
            selected_index = 0
            if selected_app_id:
                for app_idx, app in enumerate(page_apps):
                    if str(getattr(app, 'app_id', '')).strip() == selected_app_id:
                        selected_index = app_idx
                        break
            for idx, app in enumerate(page_apps):
                r = idx // self._grid_cols
                c = idx % self._grid_cols
                btn = self._make_app_button(app, icon_px=self._icon_px, show_label=True)
                grid.addWidget(btn, r, c)
                buttons.append(btn)
            self._page_buttons.append(buttons)
            self._page_selection_indices.append(min(selected_index, max(0, len(buttons) - 1)))
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
        self._sync_selection_state(focus=False)

    def _set_page(self, index: int) -> None:
        index = max(0, min(int(index), self._pages_layout.count() - 1))
        self._current_page = index
        try:
            self._pages_layout.setCurrentIndex(index)
        except Exception:
            pass
        self._update_page_dots()
        self._sync_selection_state(focus=False)

    def _all_tile_widgets(self):
        for page_buttons in self._page_buttons:
            for widget in page_buttons:
                yield widget

    def _is_tile_widget(self, obj) -> bool:
        for widget in self._all_tile_widgets():
            if widget is obj:
                return True
        return False

    def _current_page_buttons(self) -> list[QToolButton]:
        if 0 <= self._current_page < len(self._page_buttons):
            return self._page_buttons[self._current_page]
        return []

    def _current_selection_index(self) -> int:
        if 0 <= self._current_page < len(self._page_selection_indices):
            return self._page_selection_indices[self._current_page]
        return 0

    def _selected_widget_for_current_page(self):
        buttons = self._current_page_buttons()
        if not buttons:
            return None
        index = max(0, min(self._current_selection_index(), len(buttons) - 1))
        return buttons[index]

    def _sync_selection_state(self, *, focus: bool, show_highlight: bool | None = None) -> None:
        if show_highlight is None:
            show_highlight = self._keyboard_focus_visible
        for page_idx, buttons in enumerate(self._page_buttons):
            selected_index = self._page_selection_indices[page_idx] if page_idx < len(self._page_selection_indices) else 0
            for idx, widget in enumerate(buttons):
                is_selected = page_idx == self._current_page and idx == selected_index
                widget.setProperty('selected', is_selected)
                btn = widget.property('_btn')
                if btn and is_selected and show_highlight:
                    btn.setStyleSheet('QToolButton { background: rgba(255, 255, 255, 20); border: 2px solid rgba(255, 255, 255, 150); border-radius: 10px; padding: 2px; }')
                elif btn:
                    btn.setStyleSheet('QToolButton { background: transparent; border: 2px solid transparent; border-radius: 10px; padding: 2px; }')

        selected_widget = self._selected_widget_for_current_page()
        if focus and selected_widget is not None:
            try:
                selected_widget.setFocus()
            except Exception:
                pass

    def _set_selection(self, page_index: int, tile_index: int, *, focus: bool = True) -> None:
        if not self._page_buttons:
            return

        page_index = max(0, min(int(page_index), len(self._page_buttons) - 1))
        buttons = self._page_buttons[page_index]

        while len(self._page_selection_indices) < len(self._page_buttons):
            self._page_selection_indices.append(0)

        if not buttons:
            self._current_page = page_index
            self._page_selection_indices[page_index] = 0
            self._selected_app_id = None
            self._sync_selection_state(focus=focus)
            return

        tile_index = max(0, min(int(tile_index), len(buttons) - 1))
        self._current_page = page_index
        self._page_selection_indices[page_index] = tile_index

        selected_widget = buttons[tile_index]
        self._selected_app_id = str(selected_widget.property('appId') or '') or None
        try:
            self._pages_layout.setCurrentIndex(page_index)
        except Exception:
            pass
        self._update_page_dots()
        self._sync_selection_state(focus=focus)

    def _launch_selected_app(self) -> None:
        selected_widget = self._selected_widget_for_current_page()
        if selected_widget is None:
            return
        app_id = str(selected_widget.property('appId') or '').strip()
        if not app_id:
            return
        try:
            self.window.launch_app(app_id)
        except Exception:
            pass

    def _move_selection(self, row_delta: int, col_delta: int) -> None:
        buttons = self._current_page_buttons()
        if not buttons:
            return

        cols = max(1, int(self._grid_cols))
        current_index = self._current_selection_index()
        current_row = current_index // cols
        current_col = current_index % cols
        new_row = current_row + int(row_delta)
        new_col = current_col + int(col_delta)
        new_index = new_row * cols + new_col

        if 0 <= new_index < len(buttons):
            self._set_selection(self._current_page, new_index)
            return

        if col_delta < 0 and new_col < 0 and self._current_page > 0:
            previous_buttons = self._page_buttons[self._current_page - 1]
            self._set_selection(self._current_page - 1, len(previous_buttons) - 1)
            return

        if col_delta > 0 and new_col >= cols and self._current_page + 1 < len(self._page_buttons):
            self._set_selection(self._current_page + 1, 0)
            return

        if row_delta < 0 and new_row < 0 and self._current_page > 0:
            previous_buttons = self._page_buttons[self._current_page - 1]
            self._set_selection(self._current_page - 1, min(len(previous_buttons) - 1, current_col))
            return

        if row_delta > 0 and new_row * cols >= len(buttons) and self._current_page + 1 < len(self._page_buttons):
            next_buttons = self._page_buttons[self._current_page + 1]
            self._set_selection(self._current_page + 1, min(len(next_buttons) - 1, current_col))

    def _go_to_first_tile(self) -> None:
        if self._current_page_buttons():
            self._set_selection(self._current_page, 0)

    def _go_to_last_tile(self) -> None:
        buttons = self._current_page_buttons()
        if buttons:
            self._set_selection(self._current_page, len(buttons) - 1)

    def _go_to_previous_page(self) -> None:
        if self._current_page <= 0:
            return
        previous_buttons = self._page_buttons[self._current_page - 1]
        target_index = min(len(previous_buttons) - 1, self._current_selection_index()) if previous_buttons else 0
        self._set_selection(self._current_page - 1, target_index)

    def _go_to_next_page(self) -> None:
        if self._current_page + 1 >= len(self._page_buttons):
            return
        next_buttons = self._page_buttons[self._current_page + 1]
        target_index = min(len(next_buttons) - 1, self._current_selection_index()) if next_buttons else 0
        self._set_selection(self._current_page + 1, target_index)

    def _show_keyboard_focus(self) -> None:
        """Show keyboard focus highlight and start/reset the hide timer."""
        if not self._keyboard_focus_visible:
            self._keyboard_focus_visible = True
            self._sync_selection_state(focus=False, show_highlight=True)
        self._reset_keyboard_activity_timer()

    def _hide_keyboard_focus(self) -> None:
        """Hide keyboard focus highlight."""
        if self._keyboard_activity_timer is not None:
            self._keyboard_activity_timer.stop()
            self._keyboard_activity_timer = None
        if self._keyboard_focus_visible:
            self._keyboard_focus_visible = False
            self._sync_selection_state(focus=False, show_highlight=False)

    def _reset_keyboard_activity_timer(self) -> None:
        """Reset the 5-second inactivity timer."""
        if self._keyboard_activity_timer is not None:
            self._keyboard_activity_timer.stop()
        else:
            self._keyboard_activity_timer = QTimer()
            self._keyboard_activity_timer.timeout.connect(self._hide_keyboard_focus)
        self._keyboard_activity_timer.start(5000)  # 5 seconds

    def _handle_key_navigation(self, event) -> bool:
        self._show_keyboard_focus()
        key = event.key()

        # Escape key closes settings and returns to grid
        if key == Qt.Key_Escape:
            if self._settings_focused:
                self._hide_settings_panel()
                return True
            return False

        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self._settings_focused and self._settings_button is not None:
                self._show_settings_panel()
                return True
            self._launch_selected_app()
            return True

        # Handle up arrow - can navigate to settings button
        if key == Qt.Key_Up:
            if self._settings_focused:
                # Move down from settings to top row of grid
                self._settings_focused = False
                self._set_selection(self._current_page, 0, focus=True)
                return True
            else:
                current_index = self._current_selection_index()
                if current_index < self._grid_cols:
                    # At top row - move to settings button
                    self._settings_focused = True
                    if self._settings_button is not None:
                        self._settings_button.setFocus()
                    return True
                else:
                    # Normal grid navigation
                    self._move_selection(-1, 0)
                    return True

        # Handle down arrow
        if key == Qt.Key_Down:
            if self._settings_focused:
                # Settings button is focused, go to grid
                self._settings_focused = False
                self._set_selection(self._current_page, 0, focus=True)
                return True
            else:
                self._move_selection(1, 0)
                return True

        if key == Qt.Key_Left:
            self._move_selection(0, -1)
            return True
        if key == Qt.Key_Right:
            self._move_selection(0, 1)
            return True

        if key == Qt.Key_PageUp:
            self._go_to_previous_page()
            return True
        if key == Qt.Key_PageDown:
            self._go_to_next_page()
            return True

        if key == Qt.Key_Home:
            self._go_to_first_tile()
            return True
        if key == Qt.Key_End:
            self._go_to_last_tile()
            return True

        return False

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

    def _schedule_wallpaper_render(self) -> None:
        if self._wallpaper_render_scheduled:
            return
        self._wallpaper_render_scheduled = True
        QTimer.singleShot(0, self._flush_wallpaper_render)

    def _flush_wallpaper_render(self) -> None:
        self._wallpaper_render_scheduled = False
        self._render_wallpaper()

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
            for tile in page_buttons:
                tile.setFixedSize(cell_w, cell_h)

    def _create_top_bar(self) -> None:
        """Create the top bar with time display and settings button."""
        top_bar = QWidget(self._fg)
        top_bar.setFixedHeight(80)
        top_bar.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(28, 0, 28, 0)
        top_layout.setSpacing(24)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_bar.setLayout(top_layout)
        
        # Add stretch on the left to push time and settings to the right
        top_layout.addStretch()
        
        # Time label
        self._time_label = QLabel()
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._time_label.setStyleSheet(
            'QLabel { color: rgba(255, 255, 255, 235); font-size: 48px; }'
        )
        top_layout.addWidget(self._time_label)
        
        # Settings button (gear icon)
        settings_btn = QToolButton(top_bar)
        settings_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        settings_btn.setIconSize(QSize(40, 40))
        settings_btn.setAutoRaise(True)
        settings_btn.setFocusPolicy(Qt.StrongFocus)
        settings_btn.setStyleSheet(
            'QToolButton { background: transparent; border: none; color: rgba(255, 255, 255, 235); outline: none; }'
            'QToolButton:pressed { color: rgba(255, 255, 255, 255); }'
            'QToolButton:focus { color: rgba(100, 200, 255, 255); }'
        )
        
        # Create a simple gear icon using Unicode
        settings_btn.setText('⚙')
        settings_btn.setFont(QFont())
        settings_btn.font().setPointSize(22)
        
        settings_btn.clicked.connect(self._show_settings_panel)
        settings_btn.installEventFilter(self)
        top_layout.addWidget(settings_btn)
        
        # Store reference for keyboard navigation
        self._settings_button = settings_btn
        
        # Add top bar to root layout at the top
        self._root_layout.insertWidget(0, top_bar)
        
        # Update time initially
        self._update_time()

    def _update_time(self) -> None:
        """Update the time label with current time."""
        if self._time_label is not None:
            current_time = QDateTime.currentDateTime()
            time_text = current_time.toString('h:mm AP')
            self._time_label.setText(time_text)

    def _start_time_update_timer(self) -> None:
        """Start or restart the timer that updates the time display."""
        if self._time_update_timer is None:
            self._time_update_timer = QTimer(self)
            self._time_update_timer.timeout.connect(self._update_time)
        self._time_update_timer.start(1000)  # Update every second

    def _show_settings_panel(self) -> None:
        """Show the settings panel."""
        if self._settings_panel is None:
            self._create_settings_panel()
        
        if self._settings_panel is not None:
            self._settings_focused = True
            self._settings_panel.show()
            self._settings_panel.raise_()
            self._settings_panel.activateWindow()

    def _hide_settings_panel(self) -> None:
        """Hide the settings panel and return focus to grid."""
        self._settings_focused = False
        if self._settings_panel is not None:
            self._settings_panel.hide()
        # Return focus to the grid app selection
        selected_widget = self._selected_widget_for_current_page()
        if selected_widget is not None:
            selected_widget.setFocus()
        else:
            self._fg.setFocus()

    def _create_settings_panel(self) -> None:
        """Create the settings panel stub."""
        try:
            panel = QWidget(self.container)
            panel.setWindowTitle("Quick Settings")
            panel.setGeometry(self.container.width() - 500, 72, 450, 600)
            panel.setWindowFlags(Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            
            panel_layout = QVBoxLayout()
            panel_layout.setContentsMargins(24, 24, 24, 24)
            panel_layout.setSpacing(20)
            
            # Add placeholder settings
            settings_title = QLabel("Quick Settings")
            settings_title_font = QFont()
            settings_title_font.setPointSize(18)
            settings_title_font.setBold(True)
            settings_title.setFont(settings_title_font)
            settings_title.setStyleSheet('color: rgba(255, 255, 255, 235);')
            panel_layout.addWidget(settings_title)
            
            # Add placeholder items
            placeholder = QLabel("Settings panel coming soon...")
            placeholder_font = QFont()
            placeholder_font.setPointSize(14)
            placeholder.setFont(placeholder_font)
            placeholder.setStyleSheet('color: rgba(255, 255, 255, 150);')
            panel_layout.addWidget(placeholder)
            
            panel_layout.addStretch()
            
            panel.setLayout(panel_layout)
            
            # Style the panel
            panel.setStyleSheet(
                'QWidget { background: rgba(20, 20, 20, 220); border-radius: 8px; }'
                'QLabel { color: rgba(255, 255, 255, 235); }'
            )
            
            self._settings_panel = panel
        except Exception:
            pass

    def _next_page(self) -> None:
        self._go_to_next_page()

    def _prev_page(self) -> None:
        self._go_to_previous_page()

    def eventFilter(self, obj, event):
        # Handle key navigation for settings button
        if event.type() == QEvent.KeyPress and obj is self._settings_button:
            if self._handle_key_navigation(event):
                return True
        
        if event.type() == QEvent.KeyPress and (obj is self._fg or self._is_tile_widget(obj)):
            if self._handle_key_navigation(event):
                return True
        if event.type() == QEvent.FocusIn and self._is_tile_widget(obj):
            try:
                page_index = next((idx for idx, page in enumerate(self._page_buttons) if obj in page), self._current_page)
                tile_index = self._page_buttons[page_index].index(obj)
                self._set_selection(page_index, tile_index, focus=False)
            except Exception:
                pass
            return False
        if obj is self._fg and event.type() == QEvent.Resize:
            self._recompute_grid_capacity()
            self._schedule_wallpaper_render()
            return super().eventFilter(obj, event)
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
        self._schedule_wallpaper_render()
        # Re-apply styles in case dark mode changed.
        try:
            self._apply_styles()
        except Exception:
            pass

    def _render_wallpaper(self) -> None:
        # issue 
        if self._wallpaper_pix is None:
            self._bg.clear()
            return
        try:
            target = self._bg.size()
            if target.width() <= 1 or target.height() <= 1:
                # If bg hasn't been laid out yet, fall back to container size.
                target = self.container.size()
                # print(f"WINDOW SIZE:\n{self.window.size()}")
            self._bg.setPixmap(scale_crop_center(self._wallpaper_pix, target))
        except Exception:
            self._bg.clear()
