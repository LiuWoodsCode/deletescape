from __future__ import annotations

from datetime import datetime, timedelta
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QWidget,
)
from datetime import datetime, timedelta
import traceback

from config import ConfigStore, OSConfig


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        # Background task
        self._task_handle = None

        # State
        self.stopwatch_running = False
        self.stopwatch_elapsed = timedelta()
        self.timer_running = False
        self.timer_remaining = timedelta()
        self.alarms: list[str] = []

        # ROOT LAYOUT
        root = QVBoxLayout()
        container.setLayout(root)

        # TABS
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ==========================================
        # CLOCK TAB
        # ==========================================
        clock_tab = QWidget()
        clock_layout = QVBoxLayout(clock_tab)

        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setStyleSheet("font-size: 50px; font-weight: bold;")

        clock_layout.addWidget(self.clock_label)
        tabs.addTab(clock_tab, "Clock")

        # ==========================================
        # STOPWATCH TAB
        # ==========================================
        sw_tab = QWidget()
        sw_layout = QVBoxLayout(sw_tab)

        self.stopwatch_label = QLabel("00:00:00.0")
        self.stopwatch_label.setAlignment(Qt.AlignCenter)
        self.stopwatch_label.setStyleSheet("font-size: 50px; font-weight: bold;")
        sw_layout.addWidget(self.stopwatch_label)

        sw_row = QHBoxLayout()
        self.sw_start = QPushButton("Start")
        self.sw_start.clicked.connect(self._stopwatch_start)
        sw_row.addWidget(self.sw_start)

        self.sw_stop = QPushButton("Stop")
        self.sw_stop.clicked.connect(self._stopwatch_stop)
        sw_row.addWidget(self.sw_stop)

        self.sw_reset = QPushButton("Reset")
        self.sw_reset.clicked.connect(self._stopwatch_reset)
        sw_row.addWidget(self.sw_reset)

        sw_layout.addLayout(sw_row)
        tabs.addTab(sw_tab, "Stopwatch")

        # ==========================================
        # TIMER TAB
        # ==========================================
        timer_tab = QWidget()
        timer_layout = QVBoxLayout(timer_tab)

        self.timer_input = QLineEdit()
        self.timer_input.setPlaceholderText("Enter seconds")
        timer_layout.addWidget(self.timer_input)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("font-size: 50px; font-weight: bold;")
        self.timer_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_label)

        timer_row = QHBoxLayout()

        self.timer_start = QPushButton("Start")
        self.timer_start.clicked.connect(self._timer_start)
        timer_row.addWidget(self.timer_start)

        self.timer_pause = QPushButton("Pause")
        self.timer_pause.clicked.connect(self._timer_pause)
        timer_row.addWidget(self.timer_pause)

        self.timer_reset = QPushButton("Reset")
        self.timer_reset.clicked.connect(self._timer_reset)
        timer_row.addWidget(self.timer_reset)

        timer_layout.addLayout(timer_row)
        tabs.addTab(timer_tab, "Timer")

        # ==========================================
        # ALARMS TAB
        # ==========================================
        alarm_tab = QWidget()
        alarm_layout = QVBoxLayout(alarm_tab)

        alarm_row = QHBoxLayout()
        self.alarm_input = QLineEdit()
        self.alarm_input.setPlaceholderText("07:30")
        alarm_row.addWidget(self.alarm_input)

        alarm_add_btn = QPushButton("Add")
        alarm_add_btn.clicked.connect(self._alarm_add)
        alarm_row.addWidget(alarm_add_btn)

        alarm_layout.addLayout(alarm_row)

        self.alarm_list = QListWidget()
        alarm_layout.addWidget(self.alarm_list)

        alarm_del_btn = QPushButton("Delete selected alarm")
        alarm_del_btn.clicked.connect(self._alarm_delete)
        alarm_layout.addWidget(alarm_del_btn)

        tabs.addTab(alarm_tab, "Alarms")

        # Background loop
        self._start_background()

    # -------------------------------------------------------------------------
    # STOPWATCH
    # -------------------------------------------------------------------------

    def _stopwatch_start(self):
        self.stopwatch_running = True
        self.window.enable_background(True)

    def _stopwatch_stop(self):
        self.stopwatch_running = False
        self.window.enable_background(False)

    def _stopwatch_reset(self):
        self.stopwatch_running = False
        self.stopwatch_elapsed = timedelta()
        self.stopwatch_label.setText("00:00:00.0")
        self.window.enable_background(False)

    # -------------------------------------------------------------------------
    # TIMER
    # -------------------------------------------------------------------------

    def _timer_start(self):
        try:
            sec = int(self.timer_input.text())
            if not self.timer_running:
                self.timer_remaining = timedelta(seconds=sec)
        except:
            self.window.notify(title="Timer", message="Invalid input", duration_ms=2000, app_id="clock")
            return

        self.timer_running = True
        self.window.enable_background(True)

    def _timer_pause(self):
        self.timer_running = False
        self.window.enable_background(False)

    def _timer_reset(self):
        self.timer_running = False
        self.window.enable_background(False)
        self.timer_remaining = timedelta()
        self.timer_label.setText("00:00:00")

    # -------------------------------------------------------------------------
    # ALARMS
    # -------------------------------------------------------------------------

    def _alarm_add(self):
        value = self.alarm_input.text().strip()
        if ":" not in value:
            self.window.notify(title="Alarm", message="Use HH:MM format", duration_ms=2000, app_id="clock")
            return

        self.alarms.append(value)
        self.alarm_list.addItem(QListWidgetItem(value))
        self.alarm_input.clear()

    def _alarm_delete(self):
        row = self.alarm_list.currentRow()
        if row >= 0:
            self.alarm_list.takeItem(row)
            del self.alarms[row]

    # -------------------------------------------------------------------------
    # BACKGROUND LOOP
    # -------------------------------------------------------------------------

    def _start_background(self):
        """Creates a 100ms background tick."""
        try:
            self.window.enable_background(True)
        except Exception:
            pass

        if self._task_handle is not None:
            return

        _config_store = ConfigStore()
        config: OSConfig = _config_store.load()

        def _on_tick():
            now = datetime.now()

            # Update CLOCK
            if not config.use_24h_time:
                self.clock_label.setText(now.strftime("%I:%M:%S %p"))
            else:
                self.clock_label.setText(now.strftime("%H:%M:%S")) 

            # Stopwatch
            if self.stopwatch_running:
                self.stopwatch_elapsed += timedelta(milliseconds=100)
                total = self.stopwatch_elapsed
                ms = int((total.microseconds / 100000))  # tenths
                display = f"{str(total.seconds//3600).zfill(2)}:" \
                          f"{str((total.seconds//60)%60).zfill(2)}:" \
                          f"{str(total.seconds%60).zfill(2)}.{ms}"
                self.stopwatch_label.setText(display)

            # Timer
            if self.timer_running and self.timer_remaining > timedelta():
                self.timer_remaining -= timedelta(milliseconds=100)
                remaining = self.timer_remaining
                display = f"{str(remaining.seconds//3600).zfill(2)}:" \
                          f"{str((remaining.seconds//60)%60).zfill(2)}:" \
                          f"{str(remaining.seconds%60).zfill(2)}"
                self.timer_label.setText(display)

                if self.timer_remaining <= timedelta():
                    self.timer_running = False
                    raise Exception
                    self.window.notify(
                        title="Timer Done",
                        message="Time's up!",
                        duration_ms=2000,
                        app_id="clock"
                    )

            # Alarms
            now_str = now.strftime("%H:%M")
            if now_str in self.alarms:
                self.window.notify(
                    title="Alarm",
                    message=f"Alarm for {now_str}",
                    duration_ms=3500,
                    app_id="clock"
                )

        try:
            self._task_handle = self.window.register_background_task(
                _on_tick,
                interval_ms=100,
                name="clockapp_tick",
                start_immediately=True,
            )
        except Exception as e:
            traceback.print_exc()

    # -------------------------------------------------------------------------
    def on_quit(self):
        try:
            if self._task_handle is not None:
                self.window.background_tasks.cancel(self._task_handle.task_id)
        except Exception:
            pass
        self._task_handle = None