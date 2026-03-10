from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QWidget


class App:
    def __init__(self, window, container: QWidget):
        self.window = window
        self.container = container

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        container.setLayout(root)

        self._title = QLabel("Location Test")
        font = self._title.font()
        font.setPointSize(18)
        self._title.setFont(font)
        root.addWidget(self._title)

        self._labels = {}
        for key in ("latitude", "longitude", "altitude_m", "accuracy_m", "speed_mps", "heading_deg", "timestamp_unix", "provider"):
            lbl = QLabel(f"{key}: --")
            root.addWidget(lbl)
            self._labels[key] = lbl

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._update)
        root.addWidget(self._refresh_btn)

        self._timer = QTimer()
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._update)
        self._timer.start()

        self._update()

    def _fmt(self, v: Any) -> str:
        if v is None:
            return "--"
        if isinstance(v, float):
            return f"{v:.6f}" if abs(v) >= 0.000001 else f"{v}"
        return str(v)

    def _update(self) -> None:
        try:
            info = self.window.get_location_info()
            self._labels["latitude"].setText(f"latitude: {self._fmt(info.latitude)}")
            self._labels["longitude"].setText(f"longitude: {self._fmt(info.longitude)}")
            self._labels["altitude_m"].setText(f"altitude_m: {self._fmt(info.altitude_m)}")
            self._labels["accuracy_m"].setText(f"accuracy_m: {self._fmt(info.accuracy_m)}")
            self._labels["speed_mps"].setText(f"speed_mps: {self._fmt(info.speed_mps)}")
            self._labels["heading_deg"].setText(f"heading_deg: {self._fmt(info.heading_deg)}")
            ts = info.timestamp_unix
            if ts is not None:
                try:
                    ts_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
                except Exception:
                    ts_s = str(ts)
            else:
                ts_s = "--"
            self._labels["timestamp_unix"].setText(f"timestamp_unix: {ts_s}")
            self._labels["provider"].setText(f"provider: {self._fmt(info.provider)}")
        except Exception:
            # Best-effort: don't crash the shell
            pass
