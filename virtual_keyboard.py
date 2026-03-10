from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLineEdit, QPushButton, QSizePolicy, QTextEdit, QWidget


class VirtualKeyboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setFixedHeight(148)

        self._shift_enabled = False
        self._symbols_enabled = False
        self._char_buttons: list[tuple[QPushButton, str, str]] = []
        self._mode_button: QPushButton | None = None
        self._shift_button: QPushButton | None = None

        self._build_ui()
        self._refresh_key_labels()
        # Flags control when the keyboard should automatically close.
        self._close_on_focus_loss = True
        self._close_on_enter = True

    def _configure_key(self, btn: QPushButton) -> None:
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        # btn.
        # btn.setMinimumSize(0, 0)
        btn.setMinimumHeight(0)
        btn.setMaximumHeight(67)
        btn.setStyleSheet("font-size: 22px;")

    def _build_ui(self) -> None:
        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        for col in range(10):
            layout.setColumnStretch(col, 0)

        row1_norm = list("qwertyuiop")
        row1_sym = list("1234567890")
        row2_norm = list("asdfghjkl")
        row2_sym = list("@#$%&-+()")
        row3_norm = list("zxcvbnm")
        row3_sym = ["!", "?", '"', "'", ":", ";", ","]

        for col, (norm, sym) in enumerate(zip(row1_norm, row1_sym)):
            btn = QPushButton(norm)
            self._configure_key(btn)
            btn.clicked.connect(self._make_char_handler(norm, sym))
            layout.addWidget(btn, 0, col)
            self._char_buttons.append((btn, norm, sym))

        for col, (norm, sym) in enumerate(zip(row2_norm, row2_sym)):
            btn = QPushButton(norm)
            self._configure_key(btn)
            btn.clicked.connect(self._make_char_handler(norm, sym))
            layout.addWidget(btn, 1, col)
            self._char_buttons.append((btn, norm, sym))

        shift = QPushButton("⇧")
        self._configure_key(shift)
        shift.clicked.connect(self._toggle_shift)
        layout.addWidget(shift, 2, 0, 1, 2)
        self._shift_button = shift

        for idx, (norm, sym) in enumerate(zip(row3_norm, row3_sym)):
            btn = QPushButton(norm)
            self._configure_key(btn)
            btn.clicked.connect(self._make_char_handler(norm, sym))
            layout.addWidget(btn, 2, idx + 2)
            self._char_buttons.append((btn, norm, sym))

        back = QPushButton("⌫")
        self._configure_key(back)
        back.clicked.connect(self._on_backspace)
        layout.addWidget(back, 2, 9)

        mode = QPushButton("&123")
        self._configure_key(mode)
        mode.clicked.connect(self._toggle_symbols)
        layout.addWidget(mode, 3, 0, 1, 2)
        self._mode_button = mode

        comma = QPushButton(",")
        self._configure_key(comma)
        comma.clicked.connect(lambda: self._insert_text(","))
        layout.addWidget(comma, 3, 2)

        space = QPushButton(" ")
        self._configure_key(space)
        space.clicked.connect(lambda: self._insert_text(" "))
        layout.addWidget(space, 3, 3, 1, 4)

        period = QPushButton(".")
        self._configure_key(period)
        period.clicked.connect(lambda: self._insert_text("."))
        layout.addWidget(period, 3, 7)

        enter = QPushButton("⏎")
        self._configure_key(enter)
        enter.clicked.connect(self._on_enter)
        layout.addWidget(enter, 3, 8, 1, 2)

        self.setLayout(layout)

    def _active_target(self):
        return self._target_widget if hasattr(self, "_target_widget") else None

    def _insert_text(self, ch: str) -> None:
        w = self._active_target()
        if w is None:
            return
        try:
            if isinstance(w, QLineEdit):
                w.insert(ch)
            elif isinstance(w, QTextEdit):
                w.insertPlainText(ch)
            else:
                w.insert(ch)
        except Exception:
            pass

    def _make_char_handler(self, normal_char: str, symbol_char: str):
        def _handler():
            if self._symbols_enabled:
                self._insert_text(symbol_char)
                return

            ch = normal_char.upper() if self._shift_enabled else normal_char
            self._insert_text(ch)

            # Mobile-like behavior: shift is one-shot.
            if self._shift_enabled:
                self._shift_enabled = False
                self._refresh_key_labels()

        return _handler

    def _refresh_key_labels(self) -> None:
        for btn, normal_char, symbol_char in self._char_buttons:
            if self._symbols_enabled:
                btn.setText(symbol_char)
            else:
                btn.setText(normal_char.upper() if self._shift_enabled else normal_char)

        if self._mode_button is not None:
            self._mode_button.setText("Abc" if self._symbols_enabled else "&123")

        if self._shift_button is not None:
            self._shift_button.setText("⇧" if not self._shift_enabled else "⇪")

    def _toggle_shift(self) -> None:
        if self._symbols_enabled:
            return
        self._shift_enabled = not self._shift_enabled
        self._refresh_key_labels()

    def _toggle_symbols(self) -> None:
        self._symbols_enabled = not self._symbols_enabled
        if self._symbols_enabled:
            self._shift_enabled = False
        self._refresh_key_labels()

    def _on_backspace(self) -> None:
        w = self._active_target()
        if w is None:
            return
        try:
            if isinstance(w, QLineEdit):
                cur = w.cursorPosition()
                if cur > 0:
                    text = w.text()
                    text = text[: cur - 1] + text[cur:]
                    w.setText(text)
                    w.setCursorPosition(cur - 1)
            elif isinstance(w, QTextEdit):
                tc = w.textCursor()
                tc.deletePreviousChar()
                w.setTextCursor(tc)
        except Exception:
            pass

    def _on_enter(self) -> None:
        w = self._active_target()
        if w is None:
            return
        try:
            # For single-line edits, emit the returnPressed signal so
            # the host can handle an Enter (e.g., submit the field).
            if isinstance(w, QLineEdit):
                try:
                    w.returnPressed.emit()
                except Exception:
                    w.clearFocus()
                self._maybe_close_on_enter()
                return

            # For multi-line text widgets, insert a newline.
            if isinstance(w, QTextEdit):
                w.insertPlainText("\n")
                self._maybe_close_on_enter()
                return

            # Fallback: try to insert a newline if the widget supports it,
            # otherwise clear focus.
            try:
                if hasattr(w, "insert"):
                    w.insert("\n")
                    self._maybe_close_on_enter()
                    return
            except Exception:
                pass

            try:
                w.clearFocus()
            except Exception:
                pass
        except Exception:
            pass

    def _maybe_close_on_enter(self) -> None:
        if self._close_on_enter:
            self.close_keyboard()

    def close_keyboard(self) -> None:
        try:
            if hasattr(self, "_target_widget"):
                del self._target_widget
        except Exception:
            pass
        try:
            self.hide()
        except Exception:
            pass

    def show_for_widget(self, widget, *, host=None, persistent: bool = False, close_on_enter: bool = True):
        """Show keyboard and target `widget` for text insertion.
        `host` is an optional widget used to compute positioning.
        """
        self._close_on_focus_loss = not persistent
        self._close_on_enter = close_on_enter
        self._target_widget = widget
        try:
            host_widget = host if host is not None else widget.window()
            layout = host_widget.layout()
            if layout is not None and self.parentWidget() is not host_widget:
                self.setParent(host_widget)
            if layout is not None and layout.indexOf(self) == -1:
                layout.addWidget(self)

            host_h = max(1, int(host_widget.height()))
            kb_height = int(max(120, min(host_h * 0.40, host_h * 0.50)))
            self.setMaximumHeight(kb_height)
            self.updateGeometry()
        except Exception:
            pass

        self.show()
