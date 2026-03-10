from __future__ import annotations

from datetime import datetime
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._task_handle = None
        self._tick = 0

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        container.setLayout(layout)

        title = QLabel("Background Tester")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel(
            "Enable background, then go Home and open another app.\n"
            "You should keep getting notifications from this app.\n\n"
            "Note: background tasks only run after first unlock."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.status = QLabel("Status: idle")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        row = QHBoxLayout()

        self.enable_btn = QPushButton("Enable background + start")
        self.enable_btn.clicked.connect(self._start)
        row.addWidget(self.enable_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.stop_btn)

        layout.addLayout(row)

        ping = QPushButton("Send test notification")
        ping.clicked.connect(lambda: self.window.notify(title="BG Tester", message="Manual ping", duration_ms=2500))
        layout.addWidget(ping)

        layout.addStretch(1)

        # If the OS supports app_id injection, keep a copy.
        self.app_id = getattr(self, "app_id", "bgtester")

    def _start(self) -> None:
        try:
            self.window.enable_background(True)
        except Exception:
            pass

        if self._task_handle is not None:
            return

        self._tick = 0

        def _on_tick() -> None:
            self._tick += 1
            now = datetime.now().strftime("%H:%M:%S")

            text = f"Status: running | tick={self._tick} | last={now}"
            try:
                run_ui = getattr(self.window, "run_on_ui_thread", None)
                if callable(run_ui):
                    run_ui(lambda t=text: self.status.setText(t))
                else:
                    self.status.setText(text)
            except Exception:
                pass

            # Notify every 5 ticks so it's easy to see.
            if self._tick % 5 == 0:
                try:
                    self.window.notify(
                        title="BG Tester",
                        message=f"Background tick {self._tick}",
                        duration_ms=2200,
                        app_id="bgtester"
                    )
                except Exception:
                    pass

        try:
            self._task_handle = self.window.register_background_task(
                _on_tick,
                interval_ms=1000,
                name="bgtester_tick",
                start_immediately=True,
            )
        except Exception as e:
            self._task_handle = None

            # Don't silently fail: surface the error so the OS-side bug can be fixed.
            try:
                self.window.notify(
                    title="BG Tester",
                    message=f"Failed to start background task: {type(e).__name__}: {e}",
                    duration_ms=5000,
                    app_id="bgtester"
                )
            except Exception:
                pass

            try:
                traceback.print_exc()
            except Exception:
                pass

            # Keep UI state consistent: allow retry.
            self.enable_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return

        self.enable_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        try:
            self.window.notify(title="BG Tester", message="Background enabled", duration_ms=2000, app_id="bgtester")
        except Exception:
            pass

    def _stop(self) -> None:
        # Turn off background mode for this app.
        try:
            self.window.enable_background(False)
        except Exception:
            pass

        # Cancel the periodic task.
        try:
            if self._task_handle is not None:
                self.window.background_tasks.cancel(self._task_handle.task_id)
        except Exception:
            pass

        self._task_handle = None
        self.status.setText("Status: stopped")

        self.enable_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        try:
            self.window.notify(title="BG Tester", message="Stopped", duration_ms=2000, app_id="bg_tester")
        except Exception:
            pass

    def on_quit(self) -> None:
        # Ensure we don't leave tasks behind if the OS terminates the app.
        try:
            if self._task_handle is not None:
                self.window.background_tasks.cancel(self._task_handle.task_id)
        except Exception:
            pass
        self._task_handle = None
