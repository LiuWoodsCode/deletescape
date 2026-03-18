from datetime import datetime
import socket

from PySide6.QtWidgets import (
    QGridLayout, QVBoxLayout, QLabel, QWidget, QProgressBar, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import QFont
from config import DeviceConfigStore, OSBuildConfigStore
class BootInterruptController(QObject):
    def __init__(self, window, container):
        super().__init__()

        self.window = window
        self.remaining = 10
        self.interrupted = False

        # -----------------------------
        # Bottom BIOS‑style UI
        # -----------------------------
        layout = QHBoxLayout()
        layout.setContentsMargins(60, 0, 60, 30)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.progress.setFixedHeight(18)

        self.progress.setStyleSheet("""
        QProgressBar {
            background-color: #2b2b2b;
            border-radius: 4px;
        }
        QProgressBar::chunk {
            background-color: #3ea6ff;
        }
        """)

        layout.addWidget(self.progress)

        container.layout().addLayout(layout)

        # -----------------------------
        # Install GLOBAL key listener
        # -----------------------------
        window.installEventFilter(self)

        # -----------------------------
        # 100ms timer (smooth bar)
        # -----------------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    # --------------------------------
    # GLOBAL KEY INTERCEPT
    # --------------------------------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            self.interrupt("KEYPRESS")
            return True
    def interrupt(self, reason=""):
        if self.interrupted:
            return

        self.interrupted = True
        self.timer.stop()

        # BIOS-style "Boot stopped" look
        self.progress.setStyleSheet("""
            QProgressBar::chunk {
                background-color: #ffb300;
            }
        """)

        if hasattr(self, "countdown"):
            self.countdown.setText("SETUP")
    # --------------------------------
    # TIMER TICK
    # --------------------------------
    def _tick(self):

        if self.interrupted:
            return

        step = 100 / (10 * 10)  # 10 sec * 100ms ticks
        new_val = self.progress.value() + step
        self.progress.setValue(new_val)

        if new_val >= 100:
            self.timer.stop()
            self.window.launch_app(self.window.embedapp)

class InfoField(QWidget):
    def __init__(self, label: str, value: str):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        label_font = QFont("Segoe UI", 12)
        label_font.setWeight(QFont.Weight.DemiBold)

        value_font = QFont("Segoe UI", 16)
        value_font.setWeight(QFont.Weight.Bold)

        lbl = QLabel(label.upper())
        lbl.setFont(label_font)
        lbl.setStyleSheet("color:#9aa0a6;")

        val = QLabel(value)
        val.setFont(value_font)
        val.setStyleSheet("color:white;")

        layout.addWidget(lbl)
        layout.addWidget(val)

class InfoSection(QWidget):
    def __init__(self, title: str):
        super().__init__()

        self.layout = QVBoxLayout()
        self.layout.setSpacing(18)
        self.layout.setContentsMargins(30, 20, 30, 20)
        self.setLayout(self.layout)

        title_font = QFont("Segoe UI", 18)
        title_font.setWeight(QFont.Weight.Bold)

        title_lbl = QLabel(title)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color:#e8eaed;")

        self.layout.addWidget(title_lbl)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(60)
        self.grid.setVerticalSpacing(25)

        self.layout.addLayout(self.grid)

        self.setStyleSheet("""
            QWidget {
                background-color: #202124;
                border-radius: 12px;
            }
        """)

    def add(self, row, col, label, value):
        self.grid.addWidget(InfoField(label, value), row, col)


class App:
    def __init__(self, window, container):
                
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        container.setLayout(root)

        main = QGridLayout()
        main.setContentsMargins(60, 40, 60, 40)
        main.setHorizontalSpacing(40)
        main.setVerticalSpacing(40)

        root.addLayout(main)

        # Load configs
        os_cfg = OSBuildConfigStore().load()
        dev_cfg = DeviceConfigStore().load()

        print(window.embedapp)
        # Extract info
        os_name = getattr(os_cfg, "os_name", "")
        os_version = getattr(os_cfg, "os_version", "")
        os_display = f"{os_name} {os_version}"
        builder_user = getattr(os_cfg, "builder_username", "")
        builder_host = getattr(os_cfg, "builder_hostname", "")
        builder_display = f"{builder_user}@{builder_host}".strip("@")

        build_date = getattr(os_cfg, "build_datetime", "")
        try:
            build_date = datetime.fromisoformat(build_date).strftime(
                "%B %d, %Y %H:%M"
            )
        except Exception:
            pass

        ip = self._get_wlan_ip()
        net = InfoSection("Network")
        net.add(0, 0, "IP Address", ip or "Not Connected")
        net.add(1, 0, "KAngel Status", "Not inplemented")

        sys = InfoSection("System")
        sys.add(0, 0, "OS", os_display)
        sys.add(1, 0, "Built By", builder_display)
        sys.add(2, 0, "Build Date", build_date)

        dev = InfoSection("Device")
        dev.add(0, 0, "Device", f"{dev_cfg.manufacturer} {dev_cfg.model_name} (hw rev: {dev_cfg.hardware_revision})")
        dev.add(1, 0, "Serial", dev_cfg.serial_number)

        main.addWidget(net, 0, 0)
        main.addWidget(sys, 0, 1)
        main.addWidget(dev, 1, 0, 1, 2)
        self.boot_wait = BootInterruptController(window, container)

    # ---------------------------------------------------
    # FIXED VERSION — now has proper signature + behavior
    # ---------------------------------------------------
    def _get_wlan_ip(self) -> str:
        """
        Returns LAN IPv4 address.
        Raises RuntimeError if no Ethernet connectivity exists.

        This is intentional for installer-visible failure.
        """

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)

            # This never sends packets — just forces routing table lookup
            s.connect(("8.8.8.8", 80))

            ip = s.getsockname()[0]
            s.close()

            # If we got a link‑local address DHCP failed
            if ip.startswith("169.254"):
                self.network_ok = False
                return f"DHCP failed (got {ip})"
            return str(ip)
        except Exception:
            self.network_ok = False
            raise RuntimeError("NO_LAN")