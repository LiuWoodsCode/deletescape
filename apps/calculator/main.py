from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QSizePolicy


def _is_effective_int(value: float) -> bool:
    try:
        return math.isfinite(value) and abs(value - round(value)) < 1e-12
    except Exception:
        return False


def _format_number(value: float) -> str:
    if not math.isfinite(value):
        return "Error"
    if _is_effective_int(value):
        return str(int(round(value)))
    # Keep it compact for a phone-sized display.
    text = format(value, ".12g")
    return text


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._acc: float | None = None
        self._pending_op: str | None = None  # one of + - * /
        self._entry: str = ""
        self._just_evaluated = False

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        container.setLayout(root)

        self._display = QLabel("0")
        self._display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._display.setMinimumHeight(56)
        self._display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        df = QFont()
        df.setPointSize(28)
        df.setBold(True)
        self._display.setFont(df)
        self._display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._display)

        grid = QGridLayout()
        grid.setSpacing(8)
        for r in range(5):
            grid.setRowStretch(r, 1)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        root.addLayout(grid, 1)

        # Row 0
        self._add_btn(grid, "C", 0, 0, self._clear)
        self._add_btn(grid, "⌫", 0, 1, self._backspace)
        self._add_btn(grid, "÷", 0, 2, lambda: self._press_op("/"))
        self._add_btn(grid, "×", 0, 3, lambda: self._press_op("*"))

        # Row 1
        self._add_btn(grid, "7", 1, 0, lambda: self._press_digit("7"))
        self._add_btn(grid, "8", 1, 1, lambda: self._press_digit("8"))
        self._add_btn(grid, "9", 1, 2, lambda: self._press_digit("9"))
        self._add_btn(grid, "-", 1, 3, lambda: self._press_op("-"))

        # Row 2
        self._add_btn(grid, "4", 2, 0, lambda: self._press_digit("4"))
        self._add_btn(grid, "5", 2, 1, lambda: self._press_digit("5"))
        self._add_btn(grid, "6", 2, 2, lambda: self._press_digit("6"))
        self._add_btn(grid, "+", 2, 3, lambda: self._press_op("+"))

        # Row 3
        self._add_btn(grid, "1", 3, 0, lambda: self._press_digit("1"))
        self._add_btn(grid, "2", 3, 1, lambda: self._press_digit("2"))
        self._add_btn(grid, "3", 3, 2, lambda: self._press_digit("3"))
        self._add_btn(grid, "=", 3, 3, self._equals)

        # Row 4
        self._add_btn(grid, "0", 4, 0, lambda: self._press_digit("0"), col_span=2)
        self._add_btn(grid, ".", 4, 2, lambda: self._press_digit("."))
        self._add_btn(grid, "=", 4, 3, self._equals)

        self._sync_display()

    def _add_btn(self, grid: QGridLayout, text: str, row: int, col: int, handler, *, col_span: int = 1) -> None:
        btn = QPushButton(text)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setMinimumHeight(44)
        bf = btn.font()
        # Slightly larger button labels for small screens; layout will scale the buttons.
        bf.setPointSize(max(bf.pointSize(), 14))
        btn.setFont(bf)
        btn.clicked.connect(handler)
        grid.addWidget(btn, row, col, 1, col_span)

    def _sync_display(self) -> None:
        if self._entry:
            self._display.setText(self._entry)
            return

        if self._acc is None:
            self._display.setText("0")
            return

        self._display.setText(_format_number(self._acc))

    def _clear(self) -> None:
        self._acc = None
        self._pending_op = None
        self._entry = ""
        self._just_evaluated = False
        self._sync_display()

    def _backspace(self) -> None:
        if self._just_evaluated and not self._pending_op:
            # Treat post-equals as a fresh entry.
            self._acc = None
            self._entry = ""
            self._just_evaluated = False

        if not self._entry:
            return

        self._entry = self._entry[:-1]
        self._sync_display()

    def _press_digit(self, ch: str) -> None:
        if self._just_evaluated and not self._pending_op:
            # Start new calculation after '=' when typing a digit.
            self._acc = None
            self._entry = ""
            self._just_evaluated = False

        if ch == ".":
            if not self._entry:
                self._entry = "0."
            elif "." not in self._entry:
                self._entry += "."
            self._sync_display()
            return

        # ch is a digit
        if not self._entry or self._entry == "0":
            self._entry = ch
        else:
            if len(self._entry) >= 18:
                return
            self._entry += ch

        self._sync_display()

    def _press_op(self, op: str) -> None:
        # If user presses an operator right after '=', continue with accumulator.
        if self._entry:
            value = self._parse_entry()
            if value is None:
                self._error_reset()
                return

            if self._acc is None:
                self._acc = value
            elif self._pending_op is not None:
                out = self._apply(self._pending_op, self._acc, value)
                if out is None:
                    self._error_reset()
                    return
                self._acc = out
            else:
                # No pending op: replace accumulator with typed entry.
                self._acc = value

            self._entry = ""

        # Allow changing the pending op before entering the next number.
        if self._acc is None:
            self._acc = 0.0

        self._pending_op = op
        self._just_evaluated = False
        self._sync_display()

    def _equals(self) -> None:
        if self._pending_op is None:
            # No operator: just commit entry to accumulator.
            if self._entry:
                value = self._parse_entry()
                if value is None:
                    self._error_reset()
                    return
                self._acc = value
                self._entry = _format_number(value)
            self._just_evaluated = True
            self._sync_display()
            return

        if not self._entry:
            # Nothing to apply.
            self._just_evaluated = True
            self._sync_display()
            return

        if self._acc is None:
            self._acc = 0.0

        rhs = self._parse_entry()
        if rhs is None:
            self._error_reset()
            return

        out = self._apply(self._pending_op, self._acc, rhs)
        if out is None:
            self._error_reset()
            return

        self._acc = out
        self._pending_op = None
        self._entry = _format_number(out)
        self._just_evaluated = True
        self._sync_display()

    def _parse_entry(self) -> float | None:
        text = (self._entry or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None

    def _apply(self, op: str, a: float, b: float) -> float | None:
        try:
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    return None
                return a / b
        except Exception:
            return None
        return None

    def _error_reset(self) -> None:
        self._acc = None
        self._pending_op = None
        self._entry = ""
        self._just_evaluated = False
        self._display.setText("Error")

