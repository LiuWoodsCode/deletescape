from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from telephony import CallInfo, CallState, get_modem


def _format_elapsed(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._modem = get_modem()
        self._modem.call_updated.connect(self._on_call_updated)

        self._active_call: CallInfo | None = None

        root = QVBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        container.setLayout(root)

        title = QLabel("Dialer")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self._stack = QStackedLayout()
        root.addLayout(self._stack)

        self._dial_view = self._build_dial_view()
        self._in_call_view = self._build_in_call_view()

        self._stack.addWidget(self._dial_view)
        self._stack.addWidget(self._in_call_view)
        self._stack.setCurrentWidget(self._dial_view)

        # Periodic timer for call duration display.
        self._duration_timer = QTimer(container)
        self._duration_timer.setInterval(250)
        self._duration_timer.timeout.connect(self._update_duration)

        # Seed initial state.
        self._on_call_updated(self._modem.get_active_call())

    # -------------------- Dial view --------------------
    def _build_dial_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        w.setLayout(layout)

        self._number_label = QLabel("")
        self._number_label.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        self._number_label.setFont(f)
        self._number_label.setMinimumHeight(48)
        self._number_label.setText("Enter number")
        layout.addWidget(self._number_label)

        grid = QGridLayout()
        grid.setSpacing(8)
        layout.addLayout(grid)

        keys = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("*", 3, 0), ("0", 3, 1), ("#", 3, 2),
        ]

        for text, r, c in keys:
            btn = QPushButton(text)
            btn.setFixedHeight(52)
            btn.clicked.connect(lambda _, t=text: self._append_digit(t))
            grid.addWidget(btn, r, c)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        back = QPushButton("Back")
        back.clicked.connect(self._backspace)
        bottom.addWidget(back)

        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_number)
        bottom.addWidget(clear)

        layout.addLayout(bottom)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        call_btn = QPushButton("Call")
        call_btn.clicked.connect(self._start_call)
        actions.addWidget(call_btn)

        layout.addLayout(actions)
        layout.addStretch(1)

        self._dial_number = ""
        return w

    def _sync_number_label(self) -> None:
        if not self._dial_number:
            self._number_label.setText("Enter number")
        else:
            self._number_label.setText(self._dial_number)

    def _append_digit(self, d: str) -> None:
        if self._active_call is not None and self._active_call.state in {CallState.DIALING, CallState.CONNECTED, CallState.RINGING}:
            return
        if len(self._dial_number) >= 24:
            return
        self._dial_number += str(d)
        self._sync_number_label()

    def _backspace(self) -> None:
        if self._active_call is not None and self._active_call.state in {CallState.DIALING, CallState.CONNECTED, CallState.RINGING}:
            return
        self._dial_number = self._dial_number[:-1]
        self._sync_number_label()

    def _clear_number(self) -> None:
        if self._active_call is not None and self._active_call.state in {CallState.DIALING, CallState.CONNECTED, CallState.RINGING}:
            return
        self._dial_number = ""
        self._sync_number_label()

    def _start_call(self) -> None:
        number = (self._dial_number or "").strip()
        if not number:
            self.window.notify(title="Dialer", message="Enter a number", duration_ms=1800, app_id="dialer")
            return
        self._modem.dial(number)

    # -------------------- In-call view --------------------
    def _build_in_call_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        w.setLayout(layout)

        self._call_number = QLabel("")
        self._call_number.setAlignment(Qt.AlignCenter)
        nf = QFont()
        nf.setPointSize(24)
        nf.setBold(True)
        self._call_number.setFont(nf)
        layout.addWidget(self._call_number)

        self._call_status = QLabel("")
        self._call_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._call_status)

        self._call_duration = QLabel("0:00")
        self._call_duration.setAlignment(Qt.AlignCenter)
        df = QFont()
        df.setPointSize(18)
        self._call_duration.setFont(df)
        layout.addWidget(self._call_duration)

        row = QHBoxLayout()
        row.setSpacing(8)

        hang = QPushButton("Hang Up")
        hang.clicked.connect(self._modem.hang_up)
        row.addWidget(hang)

        layout.addLayout(row)

        self._after_call_hint = QLabel("")
        self._after_call_hint.setAlignment(Qt.AlignCenter)
        self._after_call_hint.setWordWrap(True)
        layout.addWidget(self._after_call_hint)

        layout.addStretch(1)
        return w

    def _update_duration(self) -> None:
        call = self._active_call
        if call is None:
            self._call_duration.setText("0:00")
            return
        if call.connected_at_monotonic is None:
            self._call_duration.setText("0:00")
            return
        elapsed = int(time.monotonic() - call.connected_at_monotonic)
        self._call_duration.setText(_format_elapsed(elapsed))

    # -------------------- Call state wiring --------------------
    def _on_call_updated(self, info: CallInfo | None) -> None:
        self._active_call = info

        if info is None:
            self._duration_timer.stop()
            self._stack.setCurrentWidget(self._dial_view)
            self._call_number.setText("")
            self._call_status.setText("")
            self._after_call_hint.setText("")
            return

        self._stack.setCurrentWidget(self._in_call_view)
        self._call_number.setText(info.number)

        if info.state == CallState.DIALING:
            self._duration_timer.stop()
            self._call_status.setText("Dialing…")
            self._after_call_hint.setText("")
            self._call_duration.setText("0:00")
            return

        if info.state == CallState.CONNECTED:
            self._call_status.setText("In call")
            self._after_call_hint.setText("")
            if not self._duration_timer.isActive():
                self._duration_timer.start()
            self._update_duration()
            return

        if info.state == CallState.ENDED:
            self._duration_timer.stop()
            self._call_status.setText("Call ended")
            self._after_call_hint.setText("Returning to dialer…")
            self._update_duration()
            return

        if info.state == CallState.FAILED:
            self._duration_timer.stop()
            self._call_status.setText("Call failed")
            self._after_call_hint.setText(info.failure_reason or "")
            self._call_duration.setText("0:00")
            return

        # Fallback
        self._duration_timer.stop()
        self._call_status.setText(str(info.state))
        self._after_call_hint.setText("")

    def on_quit(self) -> None:
        try:
            self._modem.call_updated.disconnect(self._on_call_updated)
        except Exception:
            pass
        try:
            self._duration_timer.stop()
        except Exception:
            pass
