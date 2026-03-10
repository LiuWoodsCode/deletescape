from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QCheckBox, QPushButton, QWidget, QFrame, QSlider
)
from PySide6.QtCore import Qt
from pathlib import Path

from config import DeviceConfigStore, OSBuildConfigStore
from battery import get_battery_info


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        container.setLayout(self.layout)

        self._set_view("main")

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    def _menu_button(self, text, action):
        btn = QPushButton(text)
        btn.setStyleSheet("text-align: left; padding: 12px;")
        btn.clicked.connect(action)
        return btn

    def _add_row(self, label: str, value: str):
        row = QLabel(f"{label}: {value if value else '-'}")
        row.setWordWrap(True)
        self.layout.addWidget(row)

    def _fmt_float(self, value, unit: str, decimals: int = 2) -> str:
        try:
            return f"{float(value):.{decimals}f} {unit}".strip() if value is not None else ""
        except:
            return ""

    def _fmt_int(self, value, unit="") -> str:
        try:
            suffix = f" {unit}" if unit else ""
            return f"{int(value)}{suffix}" if value is not None else ""
        except:
            return ""

    # ---------------------------------------------------------
    # Main MENU (iOS/Android style)
    # ---------------------------------------------------------
    def _set_view(self, view: str):
        self._clear_layout()

        # ---------------------------------------------------------
        # Main menu ---------------------------------------------------------
        if view == "main":
            title = QLabel("Settings")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            # Connectivity
            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Connectivity</b>"))

            self.layout.addWidget(self._menu_button("Wi‑Fi", lambda: self._set_view("wifi")))
            self.layout.addWidget(self._menu_button("Bluetooth", lambda: self._set_view("bluetooth")))
            self.layout.addWidget(self._menu_button("Cellular", lambda: self._set_view("cellular")))

            # Display
            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Display</b>"))

            self.layout.addWidget(self._menu_button("Brightness", lambda: self._set_view("display")))
            self.layout.addWidget(self._menu_button("Date/Time", lambda: self._set_view("datetime_settings")))
            self.layout.addWidget(self._menu_button("Time Format (To Be Replaced)", lambda: self._set_view("time_settings")))
            self.layout.addWidget(self._menu_button("Appearance", lambda: self._set_view("appearance")))

            # Personalization
            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Personalization</b>"))

            self.layout.addWidget(self._menu_button("Wallpaper", lambda: self._set_view("wallpaper_settings")))

            # System
            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>System</b>"))

            self.layout.addWidget(self._menu_button("Audio", lambda: self._set_view("audio")))
            self.layout.addWidget(self._menu_button("Developer Options", lambda: self._set_view("developer_options")))
            self.layout.addWidget(self._menu_button("Reset", lambda: self._set_view("reset")))
            self.layout.addWidget(self._menu_button("Battery", lambda: self._set_view("battery_info")))
            self.layout.addWidget(self._menu_button("About", lambda: self._set_view("about")))

            self.layout.addStretch(1)
            return

        # ---------------------------------------------------------
        # Submenus
        # ---------------------------------------------------------

        # Time format settings
        if view == "time_settings":
            title = QLabel("Time Format")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            use24 = QCheckBox("Use 24‑hour time")
            use24.setChecked(bool(self.window.config.use_24h_time))
            use24.toggled.connect(lambda c: self.window.set_setting("use_24h_time", bool(c)))
            self.layout.addWidget(use24)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        # Appearance submenu
        if view == "appearance":
            title = QLabel("Appearance")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            dark = QCheckBox("Dark mode")
            dark.setChecked(bool(self.window.config.dark_mode))
            dark.toggled.connect(lambda c: self.window.set_setting("dark_mode", bool(c)))
            self.layout.addWidget(dark)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        # Wallpaper submenu
        if view == "wallpaper_settings":
            title = QLabel("Wallpaper")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            lock = getattr(self.window.config, 'lock_wallpaper', '') or '(none)'
            home = getattr(self.window.config, 'home_wallpaper', '') or '(none)'

            self.layout.addWidget(QLabel(f"Lock Screen: {Path(lock).name if lock!='(none)' else lock}"))
            self.layout.addWidget(self._menu_button("Set Lock Wallpaper",
                                                    lambda: self._pick_wallpaper('lock_wallpaper', "Select lock wallpaper")))
            self.layout.addWidget(self._menu_button("Clear Lock Wallpaper",
                                                    lambda: self._clear_wallpaper('lock_wallpaper')))

            self.layout.addWidget(self._separator())

            self.layout.addWidget(QLabel(f"Home Screen: {Path(home).name if home!='(none)' else home}"))
            self.layout.addWidget(self._menu_button("Set Home Wallpaper",
                                                    lambda: self._pick_wallpaper('home_wallpaper', "Select home wallpaper")))
            self.layout.addWidget(self._menu_button("Clear Home Wallpaper",
                                                    lambda: self._clear_wallpaper('home_wallpaper')))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        if view == "wifi":
            title = QLabel("Wi‑Fi")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            wifi_toggle = QCheckBox("Wi‑Fi Enabled")
            wifi_toggle.setChecked(True)
            self.layout.addWidget(wifi_toggle)

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Available Networks</b>"))

            networks = [
                ("CoffeeShop_WiFi", True),
                ("Home‑5G", False),
                ("PixelHotspot", False),
                ("Public_WiFi", False)
            ]

            for ssid, connected in networks:
                txt = ssid + ("  ✓ Connected" if connected else "")
                self.layout.addWidget(self._menu_button(txt, lambda s=ssid: self._set_view(("wifi_network", s))))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        
        if isinstance(view, tuple) and view[0] == "wifi_network":
            ssid = view[1]
            title = QLabel(f"Network: {ssid}")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self._add_row("Status", "Connected" if ssid == "CoffeeShop_WiFi" else "Not Connected")
            self._add_row("Security", "WPA2")
            self._add_row("Signal Strength", "Excellent" if ssid == "Home‑5G" else "Good")

            self.layout.addWidget(self._menu_button("Forget Network", lambda: self._set_view("wifi")))
            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("wifi")))
            self.layout.addStretch(1)
            return
        
        if view == "bluetooth":
            title = QLabel("Bluetooth")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            bt_toggle = QCheckBox("Bluetooth Enabled")
            bt_toggle.setChecked(True)
            self.layout.addWidget(bt_toggle)

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Connected Device</b>"))
            self.layout.addWidget(QLabel("Pixel Buds Pro  ✓"))

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Available Devices</b>"))

            devices = ["Car Audio", "Keyboard‑BT", "Speaker Mini"]
            for d in devices:
                self.layout.addWidget(self._menu_button(d, lambda s=d: self._set_view(("bluetooth_device", s))))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        if isinstance(view, tuple) and view[0] == "bluetooth_device":
            dev = view[1]
            title = QLabel(dev)
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self._add_row("Status", "Not Connected")
            self._add_row("Type", "Audio Device")
            self._add_row("Battery", "Unknown")

            self.layout.addWidget(self._menu_button("Pair", lambda: self._set_view("bluetooth")))
            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("bluetooth")))
            self.layout.addStretch(1)
            return
        
        if view == "cellular":
            title = QLabel("Cellular")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self._add_row("Carrier", "Fictional Mobile LTE")
            self._add_row("Signal Strength", "•••••  (Strong)")
            self._add_row("Network Type", "4G LTE")

            data_toggle = QCheckBox("Mobile Data Enabled")
            data_toggle.setChecked(True)
            self.layout.addWidget(data_toggle)

            roaming = QCheckBox("Data Roaming")
            roaming.setChecked(False)
            self.layout.addWidget(roaming)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        if view == "datetime_settings":
            title = QLabel("Date & Time")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            # Auto toggles
            auto_time = QCheckBox("Set time automatically")
            auto_time.setChecked(True)
            self.layout.addWidget(auto_time)

            auto_date = QCheckBox("Set date automatically")
            auto_date.setChecked(True)
            self.layout.addWidget(auto_date)

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Formats</b>"))

            # 24-hour
            t24 = QCheckBox("Use 24‑hour format")
            t24.setChecked(bool(self.window.config.use_24h_time))
            t24.toggled.connect(lambda c: self.window.set_setting("use_24h_time", bool(c)))
            self.layout.addWidget(t24)

            # Show seconds
            show_sec = QCheckBox("Show seconds on clock")
            show_sec.setChecked(False)
            self.layout.addWidget(show_sec)

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Manual Date & Time</b>"))
            self.layout.addWidget(QLabel("(Disabled if automatic is on)"))

            from PySide6.QtWidgets import QDateEdit, QTimeEdit
            from PySide6.QtCore import QDate, QTime

            date_picker = QDateEdit()
            date_picker.setDate(QDate.currentDate())
            date_picker.setCalendarPopup(True)
            date_picker.setEnabled(False)
            self.layout.addWidget(date_picker)

            time_picker = QTimeEdit()
            time_picker.setTime(QTime.currentTime())
            time_picker.setDisplayFormat("HH:mm:ss" if t24.isChecked() else "hh:mm:ss AP")
            time_picker.setEnabled(False)
            self.layout.addWidget(time_picker)

            # Enable/disable based on toggles
            def update_manual():
                enable = not auto_time.isChecked() and not auto_date.isChecked()
                date_picker.setEnabled(enable)
                time_picker.setEnabled(enable)

            auto_time.toggled.connect(update_manual)
            auto_date.toggled.connect(update_manual)

            # Update formatting when 24h toggle changes
            def update_format(c):
                if c:
                    time_picker.setDisplayFormat("HH:mm:ss")
                else:
                    time_picker.setDisplayFormat("hh:mm:ss AP")

            t24.toggled.connect(update_format)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        if view == "tethering":
            title = QLabel("Tethering & Mobile Hotspot")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            hotspot = QCheckBox("Mobile Hotspot Enabled")
            hotspot.setChecked(False)
            self.layout.addWidget(hotspot)

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Hotspot Details</b>"))

            # Load (or mock) values
            ssid = getattr(self.window.config, "hotspot_ssid", "PixelProwler‑Phone")
            pwd = getattr(self.window.config, "hotspot_password", "password123")

            self._add_row("Hotspot Name", ssid)
            self.layout.addWidget(
                self._menu_button("Change Hotspot Name", lambda: self._set_view(("edit_ssid")))
            )

            self._add_row("Password", pwd)
            self.layout.addWidget(
                self._menu_button("Change Password", lambda: self._set_view(("edit_pass")))
            )

            self._add_row("Security", "WPA2‑Personal")

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Connected Devices</b>"))
            self.layout.addWidget(QLabel("0 devices connected"))

            self.layout.addWidget(self._separator())
            self.layout.addWidget(QLabel("<b>Data Usage</b>"))
            self.layout.addWidget(QLabel("Session: 0 MB"))
            self.layout.addWidget(QLabel("Monthly: 0.0 GB"))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        if view == "display":
            title = QLabel("Display")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self.layout.addWidget(QLabel("<b>Brightness</b>"))

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(50)
            self.layout.addWidget(slider)

            auto = QCheckBox("Auto‑Brightness")
            auto.setChecked(True)
            self.layout.addWidget(auto)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        
        if view == "audio":
            title = QLabel("Audio")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self.layout.addWidget(QLabel("<b>Volume</b>"))
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(50)
            self.layout.addWidget(slider)

            vibe = QCheckBox("Vibration Enabled")
            vibe.setChecked(True)
            self.layout.addWidget(vibe)

            self.layout.addWidget(self._menu_button("Ringtone (Default)", lambda: None))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        
        if view == "developer_options":
            title = QLabel("Developer Options")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            usb = QCheckBox("USB Debugging")
            usb.setChecked(False)
            self.layout.addWidget(usb)

            taps = QCheckBox("Show Visual Touches")
            taps.setChecked(False)
            self.layout.addWidget(taps)

            gpu = QCheckBox("Force GPU Rendering")
            gpu.setChecked(True)
            self.layout.addWidget(gpu)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        
        if view == "reset":
            title = QLabel("Reset Options")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            self.layout.addWidget(self._menu_button("Reset Network Settings", lambda: None))
            self.layout.addWidget(self._menu_button("Reset All Settings", lambda: None))
            self.layout.addWidget(self._menu_button("Erase All Data (Factory Reset)", lambda: None))

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return
        # ---------------------------------------------------------
        # Battery menus (same as before, just inside submenu)
        # ---------------------------------------------------------
        if view == "battery_info":
            title = QLabel("Battery")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            info = get_battery_info()

            self._add_row("Battery", self._fmt_int(info.percentage, "%"))
            self._add_row("Charging", "Yes" if info.is_charging else "No")
            self._add_row("Voltage", self._fmt_float(info.voltage, "V"))
            self._add_row("Current", self._fmt_float(info.current, "A"))
            self._add_row("Power", self._fmt_float(info.power, "W"))

            self.layout.addWidget(self._menu_button("Battery Health",
                                                    lambda: self._set_view("battery_health")))
            self.layout.addWidget(self._menu_button("Refresh",
                                                    lambda: self._set_view("battery_info")))
            self.layout.addWidget(self._menu_button("Back",
                                                    lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return

        # Battery health
        if view == "battery_health":
            title = QLabel("Battery Health")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            info = get_battery_info()
            health = info.health_percentage

            if health is not None:
                if health < 50:
                    msg = "Your battery can no longer hold a useful charge. Get it replaced by a Grizzco repair center as soon as possible."
                elif health < 80:
                    msg = "Your battery has degraded. Consider getting it replaced at a Grizzco repair center."
                else:
                    msg = None

                if msg:
                    warning = QLabel(f"<b>Important Battery Message</b><br>{msg}")
                    warning.setWordWrap(True)
                    self.layout.addWidget(warning)

            self._add_row("Battery Health", self._fmt_float(health, "%", 1))
            self._add_row("Design Capacity", self._fmt_float(info.design_capacity, "mWh", 0))
            self._add_row("Full Charge Capacity", self._fmt_float(info.full_charge_capacity, "mWh", 0))
            self._add_row("Cycle Count", self._fmt_int(info.cycle_count))

            self.layout.addWidget(self._menu_button("Refresh", lambda: self._set_view("battery_health")))
            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("battery_info")))
            self.layout.addStretch(1)
            return

        # ---------------------------------------------------------
        # About page
        # ---------------------------------------------------------
        if view == "about":
            title = QLabel("About")
            title.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(title)

            os_cfg = OSBuildConfigStore().load()
            dev_cfg = DeviceConfigStore().load()

            self._add_row("OS", os_cfg.os_name)
            self._add_row("OS Version", os_cfg.os_version)
            self._add_row("Build Number", str(os_cfg.build_number))
            self._add_row("Build ID", os_cfg.build_id)
            self._add_row("Channel", os_cfg.channel)
            self.layout.addWidget(self._separator())
            self._add_row("Manufacturer", dev_cfg.manufacturer)
            self._add_row("Model", dev_cfg.model)
            self._add_row("Model Name", dev_cfg.model_name)
            self._add_row("Serial Number", dev_cfg.serial_number)
            self._add_row("Hardware Revision", dev_cfg.hardware_revision)
            self._add_row("IMEI", dev_cfg.imei)
            self._add_row("WiFi MAC", dev_cfg.wifi_mac)
            self._add_row("Bluetooth MAC", dev_cfg.bluetooth_mac)

            self.layout.addWidget(self._menu_button("Back", lambda: self._set_view("main")))
            self.layout.addStretch(1)
            return


    # ---------------------------------------------------------
    # Wallpaper helpers
    # ---------------------------------------------------------
    def _pick_wallpaper(self, key, instruction):
        picker = getattr(self.window, 'request_photo', None)
        if not callable(picker):
            return
        path = picker(title="Select Photo", instruction=instruction)
        if not path:
            return
        self.window.set_setting(key, str(path))
        self._set_view("wallpaper_settings")

    def _clear_wallpaper(self, key):
        self.window.set_setting(key, "")
        self._set_view("wallpaper_settings")
