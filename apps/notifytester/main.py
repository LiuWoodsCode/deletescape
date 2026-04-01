from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        container.setLayout(layout)

        info = QLabel(
            "These buttons should show banner notifications just below the status bar.\n"
            "Try pressing multiple buttons quickly to verify queuing."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        row1 = QHBoxLayout()

        one = QPushButton("Notify (short)")
        one.clicked.connect(lambda: self.window.notify(title="Notify Tester", message="Hello!", duration_ms=2000, app_id="notifytester"))
        row1.addWidget(one)

        empty_msg = QPushButton("Notify (title only)")
        empty_msg.clicked.connect(lambda: self.window.notify(title="Just a title", message="", duration_ms=2000, app_id="notifytester"))
        row1.addWidget(empty_msg)

        layout.addLayout(row1)

        row2 = QHBoxLayout()

        burst = QPushButton("Queue 3")
        burst.clicked.connect(self._queue_three)
        row2.addWidget(burst)

        long_msg = QPushButton("Notify (long)")
        long_msg.clicked.connect(self._long_message)
        row2.addWidget(long_msg)

        layout.addLayout(row2)

        layout.addStretch(1)

        self.app_id = getattr(self, "app_id", "notifytester")

    def _queue_three(self) -> None:
        self.window.notify(title="Notify Tester", message="First", duration_ms=1200, app_id="notifytester")
        self.window.notify(title="Notify Tester", message="Second", duration_ms=1200, app_id="notifytester")
        self.window.notify(title="Notify Tester", message="Third", duration_ms=1200, app_id="notifytester")

    def _long_message(self) -> None:
        self.window.notify(
            title="Notify Tester",
            message="This is a longer notification message to test wrapping and sizing. "
            "It should still appear below the status bar and not break the layout.",
            duration_ms=3500,
            app_id="notifytester"
        )
