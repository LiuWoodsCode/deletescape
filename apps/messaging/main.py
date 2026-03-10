from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from telephony import TextDirection, TextMessage, get_modem


def _fmt_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M")
    except Exception:
        return ""


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._modem = get_modem()

        # Optional: if simulated modem supports incoming/sent signals, subscribe.
        try:
            self._modem.text_received.connect(self._on_text_event)
        except Exception:
            pass
        try:
            self._modem.text_sent.connect(self._on_text_event)
        except Exception:
            pass

        root = QVBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        container.setLayout(root)

        title = QLabel("Messaging")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self._stack = QStackedLayout()
        root.addLayout(self._stack)

        self._list_view = self._build_list_view()
        self._thread_view = self._build_thread_view()

        self._stack.addWidget(self._list_view)
        self._stack.addWidget(self._thread_view)
        self._stack.setCurrentWidget(self._list_view)

        self._active_peer: str | None = None

        self._reload_threads()

    # -------------------- Views --------------------
    def _build_list_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        w.setLayout(layout)

        self._threads = QListWidget()
        self._threads.itemActivated.connect(self._open_selected_thread)
        layout.addWidget(self._threads)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._new_to = QLineEdit()
        self._new_to.setPlaceholderText("New message to (number)")
        row.addWidget(self._new_to)

        new_btn = QPushButton("Open")
        new_btn.clicked.connect(self._open_new_thread)
        row.addWidget(new_btn)

        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._reload_threads)
        buttons.addWidget(refresh)
        
        layout.addLayout(buttons)
        return w

    def _build_thread_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        w.setLayout(layout)

        self._thread_title = QLabel("")
        self._thread_title.setAlignment(Qt.AlignCenter)
        tf = QFont()
        tf.setPointSize(16)
        tf.setBold(True)
        self._thread_title.setFont(tf)
        layout.addWidget(self._thread_title)

        self._messages = QListWidget()
        layout.addWidget(self._messages)

        compose_row = QHBoxLayout()
        compose_row.setSpacing(8)

        self._compose = QLineEdit()
        self._compose.setPlaceholderText("Text message")
        compose_row.addWidget(self._compose)

        send = QPushButton("Send")
        send.clicked.connect(self._send_text)
        compose_row.addWidget(send)

        layout.addLayout(compose_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        back = QPushButton("Back")
        back.clicked.connect(self._back_to_list)
        bottom.addWidget(back)

        # Dev helper: allow incoming texts if the modem is simulated.
        incoming = QPushButton("Simulate Incoming")
        incoming.clicked.connect(self._simulate_incoming)
        bottom.addWidget(incoming)

        layout.addLayout(bottom)
        return w

    # -------------------- Data --------------------
    def _history_messages(self) -> list[TextMessage]:
        modem = self._modem
        getter = getattr(modem, "get_message_history", None)
        if callable(getter):
            hist = getter()
            try:
                return hist.list_messages()
            except Exception:
                return []
        return []

    def _reload_threads(self) -> None:
        msgs = self._history_messages()

        by_peer: dict[str, list[TextMessage]] = defaultdict(list)
        for m in msgs:
            if not m.peer:
                continue
            by_peer[m.peer].append(m)

        peers = sorted(by_peer.keys(), key=lambda p: (by_peer[p][-1].timestamp_unix if by_peer[p] else 0.0), reverse=True)

        self._threads.clear()
        for peer in peers:
            thread_msgs = by_peer[peer]
            last = thread_msgs[-1] if thread_msgs else None
            preview = (last.body[:32] + "…") if last and len(last.body) > 32 else (last.body if last else "")
            stamp = _fmt_time(last.timestamp_unix) if last else ""
            text = f"{peer}  {stamp}\n{preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, peer)
            self._threads.addItem(item)

    def _open_selected_thread(self) -> None:
        item = self._threads.currentItem()
        if item is None:
            return
        peer = item.data(Qt.UserRole)
        if not isinstance(peer, str) or not peer.strip():
            return
        self._open_thread(peer.strip())

    def _open_new_thread(self) -> None:
        peer = (self._new_to.text() or "").strip()
        if not peer:
            self.window.notify(title="Messaging", message="Enter a number", duration_ms=1800, app_id="messaging")
            return
        self._new_to.setText("")
        self._open_thread(peer)

    def _open_thread(self, peer: str) -> None:
        self._active_peer = peer
        self._thread_title.setText(peer)
        self._render_thread()
        self._stack.setCurrentWidget(self._thread_view)

    def _render_thread(self) -> None:
        peer = self._active_peer
        if not peer:
            return

        msgs = [m for m in self._history_messages() if m.peer == peer]
        msgs.sort(key=lambda m: m.timestamp_unix)

        self._messages.clear()
        for m in msgs:
            prefix = "Me" if m.direction == TextDirection.OUTGOING else "Them"
            stamp = _fmt_time(m.timestamp_unix)
            item = QListWidgetItem(f"{prefix}  {stamp}\n{m.body}")
            self._messages.addItem(item)

        if self._messages.count() > 0:
            self._messages.scrollToBottom()

    # -------------------- Actions --------------------
    def _send_text(self) -> None:
        peer = (self._active_peer or "").strip()
        body = (self._compose.text() or "").strip()
        if not peer:
            self.window.notify(title="Messaging", message="No thread selected", duration_ms=1800, app_id="messaging")
            return
        if not body:
            self.window.notify(title="Messaging", message="Enter a message", duration_ms=1800, app_id="messaging")
            return

        sender = getattr(self._modem, "send_text", None)
        if not callable(sender):
            self.window.notify(title="Messaging", message="Modem doesn't support texts", duration_ms=2200, app_id="messaging")
            return

        sender(peer, body)
        self._compose.setText("")
        self._render_thread()
        self._reload_threads()

    def _simulate_incoming(self) -> None:
        peer = (self._active_peer or "").strip()
        if not peer:
            return
        fn = getattr(self._modem, "simulate_incoming_text", None)
        if not callable(fn):
            self.window.notify(title="Messaging", message="Only available on simulated modem", duration_ms=2200, app_id="messaging")
            return
        fn(peer, "Hello from the simulated network")

    def _back_to_list(self) -> None:
        self._active_peer = None
        self._stack.setCurrentWidget(self._list_view)
        self._reload_threads()

    def _on_text_event(self, _msg: TextMessage) -> None:
        # Refresh views if we're visible.
        if self._active_peer:
            self._render_thread()
        self._reload_threads()

    def on_quit(self) -> None:
        try:
            self._modem.text_received.disconnect(self._on_text_event)
        except Exception:
            pass
        try:
            self._modem.text_sent.disconnect(self._on_text_event)
        except Exception:
            pass
