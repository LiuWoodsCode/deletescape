# win10m_settings_mock.py
# PySide6 recreation (lightweight) of the Windows 10 Mobile Settings app shell.
# Windows 11 23H2 target. No extra deps besides PySide6.

from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QSize, Signal, QDate, QTime
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from battery import get_battery_info
from config import DeviceConfigStore, OSBuildConfigStore
from wifi import (
    get_wifi_info,
    scan_wifi_networks,
    list_wifi_profiles,
    add_wifi_profile,
    delete_wifi_profile,
)

# --------- theme helpers ---------

def get_windows_accent_color(default: QColor = QColor("#0078D7")) -> QColor:
    return default

ACCENT = QColor("#FF00AA")  # user's Windows accent color or fallback
BG = QColor("#000000")
PANEL = QColor("#0B0B0B")
PANEL2 = QColor("#121212")
TEXT = QColor("#FFFFFF")
MUTED = QColor("#B8B8B8")
DIVIDER = QColor("#1E1E1E")


def qcolor_css(c: QColor) -> str:
    return f"rgb({c.red()},{c.green()},{c.blue()})"


def make_glyph_icon(glyph: str, size: int = 18, color: QColor = ACCENT) -> QIcon:
    """
    Uses Segoe MDL2 Assets glyphs (available on Windows). Falls back gracefully if missing.
    """
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(color)

    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(int(size * 1.6))
    p.setFont(font)

    # center glyph
    rect = pm.rect()
    p.drawText(rect, Qt.AlignCenter, glyph)
    p.end()

    return QIcon(pm)


# Segoe MDL2 glyphs (common)
GLYPH_GEAR = "\uE713"
GLYPH_SYSTEM = "\ue8ea"
GLYPH_NETWORK = "\uE770"
GLYPH_UPDATE = "\uE770"
GLYPH_PERSONALIZE = "\ue771"
GLYPH_INTERNET = "\ue774"
GLYPH_DEVICES = "\ue772"
GLYPH_TIMELANG = "\ue775"
GLYPH_ACCESS = "\ue776"
GLYPH_UPDATE = "\ue895"
GLYPH_TEST = "\ue978" 
GLYPH_CHEVRON_RIGHT = "\uE76C"
GLYPH_BACK = "\uE72B"


# --------- small UI primitives ---------

class Divider(QFrame):
    def __init__(self, thickness: int = 1):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setFixedHeight(thickness)
        self.setStyleSheet(f"background: {qcolor_css(DIVIDER)};")


class HeaderBar(QWidget):
    backClicked = Signal()

    def __init__(self, title: str, show_back: bool, left_icon: Optional[QIcon] = None):
        super().__init__()
        self._title = QLabel(title)
        self._title.setObjectName("HeaderTitle")

        self._back = QToolButton()
        self._back.setIcon(make_glyph_icon(GLYPH_BACK, 18, TEXT))
        self._back.setIconSize(QSize(18, 18))
        self._back.setAutoRaise(True)
        self._back.clicked.connect(self.backClicked.emit)

        self._left_icon = QLabel()
        self._left_icon.setFixedSize(22, 22)
        if left_icon is not None:
            self._left_icon.setPixmap(left_icon.pixmap(22, 22))
        else:
            self._left_icon.hide()

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 12)
        row.setSpacing(10)

        if show_back:
            row.addWidget(self._back, 0, Qt.AlignVCenter)
        else:
            self._back.hide()

        row.addWidget(self._left_icon, 0, Qt.AlignVCenter)
        row.addWidget(self._title, 1, Qt.AlignVCenter)

        self.setStyleSheet(
            f"""
            QLabel#HeaderTitle {{
                color: {qcolor_css(TEXT)};
                font-size: 22px;
                font-weight: 600;
            }}
            QToolButton {{
                color: {qcolor_css(TEXT)};
            }}
            """
        )

class NavRowItem(QFrame):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", icon: Optional[QIcon] = None):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self._search_title = title
        self._search_subtitle = subtitle

        self.setStyleSheet(
            f"""
            QFrame {{
                background: transparent;
            }}
            QFrame:hover {{
                background: {qcolor_css(PANEL2)};
            }}
            """
        )
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        if icon:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon.pixmap(24, 24))
            root.addWidget(icon_lbl, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(
            f"color: {qcolor_css(TEXT)}; font-size: 16px; font-weight: 600;"
        )

        text_col.addWidget(self.title_lbl)

        if subtitle:
            self.sub_lbl = QLabel(subtitle)
            self.sub_lbl.setStyleSheet(
                f"color: {qcolor_css(MUTED)}; font-size: 12px;"
            )
            text_col.addWidget(self.sub_lbl)

        root.addLayout(text_col, 1)

        chev = QLabel()
        chev.setPixmap(make_glyph_icon(GLYPH_CHEVRON_RIGHT, 14, MUTED).pixmap(14, 14))
        root.addWidget(chev, 0, Qt.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class SectionTitle(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {qcolor_css(TEXT)};
                font-size: 22px;
                font-weight: 600;
                padding: 4px 0px;
            }}
            """
        )


class SubHeading(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {qcolor_css(TEXT)};
                font-size: 18px;
                font-weight: 600;
                padding: 14px 0px 6px 0px;
            }}
            """
        )


class InfoRow(QWidget):
    def __init__(self, label: str, value: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        left = QLabel(label)
        left.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
        right = QLabel(value)
        right.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
        right.setWordWrap(True)

        row.addWidget(left, 0, Qt.AlignTop)
        row.addWidget(right, 1, Qt.AlignTop)


# --------- page model ---------

@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    build: Callable[[], QWidget]


# --------- pages ---------

class HubPage(QWidget):
    """
    Main "Settings" hub: search + section list.
    """
    navigateToSection = Signal(str)  # section_key

    def __init__(self, sections: List[tuple[str, str, str, QIcon]]):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Settings", show_back=False, left_icon=make_glyph_icon(GLYPH_GEAR, 18, ACCENT))
        root.addWidget(header)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 6, 16, 16)
        body_l.setSpacing(12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a setting")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(36)
        self.search.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid {qcolor_css(MUTED)};
                border-radius: 2px;
                padding: 6px 10px;
                color: {qcolor_css(TEXT)};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {qcolor_css(ACCENT)};
            }}
            """
        )
        body_l.addWidget(self.search)

        # sections list
        list_wrap = QFrame()
        list_wrap.setStyleSheet(f"background: transparent; border: none;")
        lw_l = QVBoxLayout(list_wrap)
        lw_l.setContentsMargins(0, 0, 0, 0)
        lw_l.setSpacing(0)

        self._buttons: Dict[str, NavRowItem] = {}

        for section_key, title, subtitle, icon in sections:
            btn = NavRowItem(title, subtitle, icon)
            btn.clicked.connect(lambda _=False, k=section_key: self.navigateToSection.emit(k))
            lw_l.addWidget(btn)
            lw_l.addWidget(Divider())
            self._buttons[section_key] = btn

        # remove last divider spacing: keep it, matches list feel
        lw_l.addStretch()
        body_l.addWidget(list_wrap)

        root.addWidget(body, 1)

        # rudimentary search filter for sections
        self.search.textChanged.connect(self._apply_filter)

    def _apply_filter(self, text: str) -> None:
        t = (text or "").strip().lower()
        for k, btn in self._buttons.items():
            visible = True
            internal_title = btn._search_title.lower()
            internal_sub = btn._search_subtitle.lower()
            if t:
                visible = (t in internal_title) or (t in internal_sub) or (t in k.lower())
            btn.setVisible(visible)


class SectionIndexPage(QWidget):
    """
    A section page: header + list of pages.
    """
    navigateToPage = Signal(str)  # page_key
    backToHub = Signal()

    def __init__(self, section_title: str, pages: List[tuple[str, str, str, Optional[QIcon]]]):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar(section_title, show_back=True, left_icon=None)
        header.backClicked.connect(self.backToHub.emit)
        root.addWidget(header)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 8, 16, 16)
        body_l.setSpacing(12)

        search = QLineEdit()
        search.setPlaceholderText("Find a setting")
        search.setClearButtonEnabled(True)
        search.setFixedHeight(36)
        search.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid {qcolor_css(MUTED)};
                border-radius: 2px;
                padding: 6px 10px;
                color: {qcolor_css(TEXT)};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {qcolor_css(ACCENT)};
            }}
            """
        )
        body_l.addWidget(search)

        list_wrap = QFrame()
        lw_l = QVBoxLayout(list_wrap)
        lw_l.setContentsMargins(0, 0, 0, 0)
        lw_l.setSpacing(0)

        self._page_btns: Dict[str, NavRowItem] = {}
        for page_key, title, subtitle, icon in pages:
            btn = NavRowItem(title, subtitle, icon)
            btn.clicked.connect(lambda _=False, k=page_key: self.navigateToPage.emit(k))
            lw_l.addWidget(btn)
            lw_l.addWidget(Divider())
            self._page_btns[page_key] = btn

        lw_l.addStretch()
        body_l.addWidget(list_wrap)
        root.addWidget(body, 1)

        search.textChanged.connect(lambda t: self._filter_pages(t))

    def _filter_pages(self, text: str) -> None:
        t = (text or "").strip().lower()
        for k, btn in self._page_btns.items():
            title = btn._search_title.lower()
            sub = btn._search_subtitle.lower()
            visible = True
            if t:
                visible = (t in title) or (t in sub) or (t in k.lower())
            btn.setVisible(visible)


class AboutPhonePage(QWidget):
    backRequested = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("About", show_back=True, left_icon=make_glyph_icon(GLYPH_GEAR, 18, ACCENT))
        header.backClicked.connect(self.backRequested.emit)
        root.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"""
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {qcolor_css(DIVIDER)};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """
        )

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 20)
        c.setSpacing(8)

        # Device name
        c.addWidget(SubHeading("Device name"))
        device_name = QLabel("Windows phone")
        device_name.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px; padding: 0px 0px 6px 0px;")
        c.addWidget(device_name)

        edit = QPushButton("Edit name")
        edit.setFixedWidth(110)
        edit.setFixedHeight(36)
        edit.setCursor(Qt.PointingHandCursor)
        edit.setStyleSheet(
            f"""
            QPushButton {{
                background: {qcolor_css(PANEL2)};
                border: 1px solid {qcolor_css(DIVIDER)};
                color: {qcolor_css(TEXT)};
                border-radius: 2px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                border: 1px solid {qcolor_css(MUTED)};
            }}
            QPushButton:pressed {{
                border: 1px solid {qcolor_css(ACCENT)};
            }}
            """
        )
        c.addWidget(edit, 0, Qt.AlignLeft)

        # Device info
        c.addSpacing(10)
        c.addWidget(SubHeading("Device information"))

        # Recreate rows from your screenshot
        rows = [
            ("Model:", "Microsoft Lumia 950 XL"),
            ("Carrier:", "Operator"),
            ("Software:", "Windows 10 Mobile"),
            ("Installed RAM:", "3 GB"),
            ("Version:", "1703"),
            ("OS build:", "10.0.15063.1000.rs2_release_apps.20170305-1700"),
            ("Firmware revision number:", "01078.00053.14992.0"),
            ("Hardware revision number:", "2.0.1.3"),
            ("Bootloader version:", "0"),
            ("Radio software version:", "BO25c43.00024.0001"),
            ("Radio hardware version:", "0"),
            ("Chip SOC version:", "8994"),
            ("Screen resolution:", "1440x2560"),
        ]
        for label, value in rows:
            c.addWidget(InfoRow(label, value))

        c.addItem(QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))

        scroll.setWidget(content)
        root.addWidget(scroll, 1)


# --------- Test pages ---------

class TestHomePage(QWidget):
    backRequested = Signal()
    openTestPage = Signal(str)

    def __init__(self, pages: List[tuple[str, str, str, Optional[QIcon]]], title: str = "Test"):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar(title, show_back=True, left_icon=None)
        header.backClicked.connect(self.backRequested.emit)
        root.addWidget(header)

        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(16, 8, 16, 16)
        b.setSpacing(12)

        search = QLineEdit()
        search.setPlaceholderText("Find a test page")
        search.setClearButtonEnabled(True)
        search.setFixedHeight(36)
        search.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: 1px solid {qcolor_css(MUTED)};
                border-radius: 2px;
                padding: 6px 10px;
                color: {qcolor_css(TEXT)};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {qcolor_css(ACCENT)};
            }}
            """
        )
        b.addWidget(search)

        list_wrap = QFrame()
        lw = QVBoxLayout(list_wrap)
        lw.setContentsMargins(0, 0, 0, 0)
        lw.setSpacing(0)

        self._btns: Dict[str, NavRowItem] = {}
        for key, t, sub, icon in pages:
            btn = NavRowItem(t, sub, icon)
            btn.clicked.connect(lambda _=False, k=key: self.openTestPage.emit(k))
            lw.addWidget(btn)
            lw.addWidget(Divider())
            self._btns[key] = btn

        lw.addStretch()
        b.addWidget(list_wrap)
        root.addWidget(body, 1)

        search.textChanged.connect(lambda t: self._filter(t))

    def _filter(self, text: str) -> None:
        t = (text or "").strip().lower()
        for k, btn in self._btns.items():
            title = btn._search_title.lower()
            sub = btn._search_subtitle.lower()
            visible = True
            if t:
                visible = (t in title) or (t in sub) or (t in k.lower())
            btn.setVisible(visible)


class SimpleTestPage(QWidget):
    backRequested = Signal()

    def __init__(self, title: str, build_body: Callable[[QVBoxLayout], None]):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar(title, show_back=True, left_icon=None)
        header.backClicked.connect(self.backRequested.emit)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 20)
        c.setSpacing(12)

        build_body(c)

        c.addItem(QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        scroll.setWidget(content)

        root.addWidget(scroll, 1)


# --------- main window / navigation ---------

class SettingsWindow(QMainWindow):
    def __init__(self, host_window=None):
        super().__init__()
        self.host_window = host_window
        self.setWindowTitle("Settings")
        self.setMinimumSize(420, 720)
        self.resize(480, 860)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # build pages
        self._pages: Dict[str, QWidget] = {}

        # Hub sections
        sections = [
            ("connectivity", "Network & internet", "Wi-Fi, Bluetooth, cellular", make_glyph_icon(GLYPH_INTERNET, 18, ACCENT)),
            ("personalization", "Personalization", "Wallpaper, appearance", make_glyph_icon(GLYPH_PERSONALIZE, 18, ACCENT)),
            ("time_and_language", "Time and language", "Date, time & formats", make_glyph_icon(GLYPH_TIMELANG, 18, ACCENT)),
            ("system", "System", "Display, notifications, battery", make_glyph_icon(GLYPH_SYSTEM, 18, ACCENT)),
            ("update", "Update and security", "Deletescape Update, backup, recovery", make_glyph_icon(GLYPH_UPDATE, 18, ACCENT)),
            ("test", "Test", "Control test pages", make_glyph_icon(GLYPH_TEST, 18, ACCENT)),
        ]
        hub = HubPage(sections)
        hub.navigateToSection.connect(self._open_section)
        self._add_page("hub", hub)
        
        # Section indices
        connectivity_pages = [
            ("connectivity.wifi", "Wi-Fi", "Manage networks", None),
            ("connectivity.bluetooth", "Bluetooth", "Paired and available devices", None),
            ("connectivity.cellular", "Cellular", "Carrier and mobile data", None),
            ("connectivity.tethering", "Tethering & hotspot", "Hotspot name and password", None),
        ]
        connectivity_index = SectionIndexPage("Network and internet", connectivity_pages)
        connectivity_index.backToHub.connect(lambda: self._go("hub"))
        connectivity_index.navigateToPage.connect(self._go)
        self._add_page("section.connectivity", connectivity_index)

        personalization_pages = [
            ("personalization.wallpaper", "Wallpaper", "Lock and home wallpapers", None),
            ("personalization.appearance", "Appearance", "Theme options", None),
        ]
        personalization_index = SectionIndexPage("Personalization", personalization_pages)
        personalization_index.backToHub.connect(lambda: self._go("hub"))
        personalization_index.navigateToPage.connect(self._go)
        self._add_page("section.personalization", personalization_index)

        
        system_pages = [
            ("system.display", "Display", "Brightness and auto-brightness", None),
            ("system.audio", "Audio", "Volume and vibration", None),
            ("system.developer", "Developer options", "Debug and rendering toggles", None),
            ("system.battery", "Battery", "Battery status and metrics", None),
            ("system.battery_health", "Battery health", "Capacity and cycle count", None),
            ("system.about", "About phone", "", None),
        ]
        system_index = SectionIndexPage("System", system_pages)
        system_index.backToHub.connect(lambda: self._go("hub"))
        system_index.navigateToPage.connect(self._go)
        self._add_page("section.system", system_index)

        # Deletescape Updates (Update & Security) — includes reset and developer links
        update_pages = [
            ("update.check", "Check for updates", "Download and install updates", None),
            ("update.security", "Security", "Security, backup and recovery", None),
            ("trouble.reset", "Reset", "Network and factory reset options", None),
            ("system.developer", "Developer options", "Debug and rendering toggles", None),
        ]
        update_index = SectionIndexPage("Update and security", update_pages)
        update_index.backToHub.connect(lambda: self._go("hub"))
        update_index.navigateToPage.connect(self._go)
        self._add_page("section.update", update_index)

        time_language_pages = [
            ("system.datetime", "Date & time", "Automatic time and format", None),
            ("system.timeformat", "Time format", "24-hour clock option", None),
        ]
        time_language_index = SectionIndexPage("Time and language", time_language_pages)
        time_language_index.backToHub.connect(lambda: self._go("hub"))
        time_language_index.navigateToPage.connect(self._go)
        self._add_page("section.time_and_language", time_language_index)

        test_index_pages = [
            ("test.buttons", "Buttons", "Push buttons, tool buttons", None),
            ("test.text", "Text input", "Line edits, placeholder, clear button", None),
            ("test.lists", "Lists", "List rows, separators", None),
            ("test.misc", "Misc", "Spacing, headings, dividers", None),
        ]
        test_index = SectionIndexPage("Test", [("test.home", "All test pages", "", None)])
        test_index.backToHub.connect(lambda: self._go("hub"))
        test_index.navigateToPage.connect(self._go)
        self._add_page("section.test", test_index)

        # Connectivity pages
        self._add_page("connectivity.wifi", self._make_connectivity_wifi())
        self._add_page("connectivity.bluetooth", self._make_connectivity_bluetooth())
        self._add_page("connectivity.cellular", self._make_connectivity_cellular())
        self._add_page("connectivity.tethering", self._make_connectivity_tethering())

        # Personalization pages
        self._add_page("personalization.wallpaper", self._make_personalization_wallpaper())
        self._add_page("personalization.appearance", self._make_personalization_appearance())

        # Time and language pages
        self._add_page("system.datetime", self._make_system_datetime())
        self._add_page("system.timeformat", self._make_system_timeformat())

        # Updates pages (mockups)
        self._add_page("update.check", self._make_update_check())
        self._add_page("update.security", self._make_update_security())

        # System pages
        self._add_page("system.display", self._make_system_display())
        self._add_page("system.audio", self._make_system_audio())
        self._add_page("system.developer", self._make_system_developer())
        self._add_page("system.battery", self._make_system_battery())
        self._add_page("system.battery_health", self._make_system_battery_health())
        self._add_page("system.about", self._make_system_about())

        # Troubleshooting pages
        self._add_page("trouble.reset", self._make_system_reset())
        
        # Test home
        test_home = TestHomePage(test_index_pages)
        test_home.backRequested.connect(lambda: self._go("hub"))
        test_home.openTestPage.connect(self._go)
        self._add_page("test.home", test_home)

        # Test pages
        self._add_page("test.buttons", self._make_test_buttons())
        self._add_page("test.text", self._make_test_text())
        self._add_page("test.lists", self._make_test_lists())
        self._add_page("test.misc", self._make_test_misc())

        self._go("hub")
        
    def _open_section(self, section_key: str) -> None:
        if section_key == "connectivity":
            self._go("section.connectivity")
        elif section_key == "personalization":
            self._go("section.personalization")
        elif section_key == "time_and_language":
            self._go("section.time_and_language")
        elif section_key == "update":
            self._go("section.update")
        elif section_key == "system":
            self._go("section.system")
        elif section_key == "test":
            # directly to test home (more useful), but keep "TEST" index page around
            self._go("test.home")
        else:
            self._go("hub")

    def close(self):
        try:
            self._window.close()
        except Exception:
            pass

    def _add_page(self, key: str, w: QWidget) -> None:
        page_widget = self._ensure_scroll_container(w)
        self._pages[key] = page_widget
        self.stack.addWidget(page_widget)

    def _ensure_scroll_container(self, page: QWidget) -> QWidget:
        if self._has_scroll_area(page):
            return page

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _has_scroll_area(self, page: QWidget) -> bool:
        if isinstance(page, QScrollArea):
            return True
        try:
            return len(page.findChildren(QScrollArea)) > 0
        except Exception:
            return False

    def _go(self, key: str) -> None:
        w = self._pages.get(key)
        if w is None:
            return
        self.stack.setCurrentWidget(w)

    def _make_button(self, text: str, on_click: Optional[Callable[[], None]] = None) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(38)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                background: {qcolor_css(PANEL2)};
                border: 1px solid {qcolor_css(DIVIDER)};
                color: {qcolor_css(TEXT)};
                border-radius: 2px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                border: 1px solid {qcolor_css(MUTED)};
            }}
            QPushButton:pressed {{
                border: 1px solid {qcolor_css(ACCENT)};
            }}
            """
        )
        if on_click is not None:
            btn.clicked.connect(on_click)
        return btn

    def _make_checkbox(self, text: str, checked: bool = False) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet(
            f"""
            QCheckBox {{
                color: {qcolor_css(TEXT)};
                font-size: 14px;
                spacing: 8px;
            }}
            """
        )
        return cb

    def _make_slider(self, value: int = 50) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(value)
        return slider

    def _add_info_rows(self, layout: QVBoxLayout, rows: List[tuple[str, str]]) -> None:
        for label, value in rows:
            layout.addWidget(InfoRow(f"{label}:", value if value else "-"))

    def _fmt_float(self, value, unit: str, decimals: int = 2) -> str:
        try:
            if value is None:
                return ""
            return f"{float(value):.{decimals}f} {unit}".strip()
        except Exception:
            return ""

    def _fmt_int(self, value, unit: str = "") -> str:
        try:
            if value is None:
                return ""
            suffix = f" {unit}" if unit else ""
            return f"{int(value)}{suffix}"
        except Exception:
            return ""

    def _make_connectivity_wifi(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Wi-Fi", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("section.connectivity"))
        root.addWidget(header)

        stack = QStackedWidget()
        root.addWidget(stack, 1)

        list_page = QWidget()
        l = QVBoxLayout(list_page)
        l.setContentsMargins(16, 12, 16, 16)
        l.setSpacing(10)

        info_label = QLabel()
        info_label.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")

        wifi_enabled_cb = self._make_checkbox("Wi-Fi Enabled", True)
        wifi_enabled_cb.setEnabled(False)
        l.addWidget(wifi_enabled_cb)
        l.addWidget(info_label)

        l.addWidget(SubHeading("Saved Profiles"))
        profiles_wrap = QWidget()
        profiles_layout = QVBoxLayout(profiles_wrap)
        profiles_layout.setContentsMargins(0, 0, 0, 0)
        profiles_layout.setSpacing(6)
        l.addWidget(profiles_wrap)

        add_ssid = QLineEdit()
        add_ssid.setPlaceholderText("SSID")
        add_ssid.setFixedHeight(34)
        add_pwd = QLineEdit()
        add_pwd.setPlaceholderText("Password (optional)")
        add_pwd.setEchoMode(QLineEdit.Password)
        add_pwd.setFixedHeight(34)
        l.addWidget(add_ssid)
        l.addWidget(add_pwd)

        add_btn = self._make_button("Add Profile")
        l.addWidget(add_btn)

        l.addWidget(SubHeading("Available Networks"))
        nets_wrap = QWidget()
        nets_layout = QVBoxLayout(nets_wrap)
        nets_layout.setContentsMargins(0, 0, 0, 0)
        nets_layout.setSpacing(6)
        l.addWidget(nets_wrap)

        refresh_btn = self._make_button("Refresh")
        l.addWidget(refresh_btn)

        detail = QWidget()
        d = QVBoxLayout(detail)
        d.setContentsMargins(16, 12, 16, 16)
        d.setSpacing(10)
        def _notify(msg: str) -> None:
            try:
                if self.host_window is not None and hasattr(self.host_window, "notify"):
                    self.host_window.notify(title="Wi-Fi", message=str(msg), duration_ms=2200)
            except Exception:
                pass

        def _host_or_module(name: str, fallback):
            fn = getattr(self.host_window, name, None) if self.host_window is not None else None
            return fn if callable(fn) else fallback

        def _clear_layout(layout: QVBoxLayout) -> None:
            while layout.count() > 0:
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        def _open_profile_detail(ssid: str, secure: Optional[bool], is_connected: bool, signal: Optional[int]) -> None:
            _clear_layout(d)
            d.addWidget(SubHeading(f"Network: {ssid}"))
            d.addWidget(InfoRow("Status:", "Connected" if is_connected else "Saved"))
            if secure is None:
                sec_text = "Unknown"
            else:
                sec_text = "Secured" if secure else "Open"
            d.addWidget(InfoRow("Security:", sec_text))
            if signal is not None:
                d.addWidget(InfoRow("Signal Strength:", f"{int(signal)}%"))
            del_btn = self._make_button("Delete Profile")

            def _delete() -> None:
                delete_fn = _host_or_module("delete_wifi_profile", delete_wifi_profile)
                ok = bool(delete_fn(ssid))
                _notify("Profile deleted" if ok else "Delete failed")
                _refresh_wifi()
                stack.setCurrentWidget(list_page)

            del_btn.clicked.connect(_delete)
            d.addWidget(del_btn)
            d.addWidget(self._make_button("Back", lambda: stack.setCurrentWidget(list_page)))
            d.addStretch(1)
            stack.setCurrentWidget(detail)

        def _refresh_wifi() -> None:
            info_fn = _host_or_module("get_wifi_info", get_wifi_info)
            scan_fn = _host_or_module("scan_wifi_networks", scan_wifi_networks)
            profiles_fn = _host_or_module("list_wifi_profiles", list_wifi_profiles)

            info = info_fn()
            networks = list(scan_fn() or [])
            profiles = list(profiles_fn() or [])

            wifi_enabled_cb.setChecked(bool(getattr(info, "enabled", False)))
            info_label.setText(
                f"Driver: {str(getattr(info, 'driver', 'unknown') or 'unknown')}"
                + (f" • Connected: {getattr(info, 'ssid', '')}" if getattr(info, "connected", False) and getattr(info, "ssid", None) else "")
            )

            _clear_layout(profiles_layout)
            if not profiles:
                profiles_layout.addWidget(QLabel("No saved profiles"))
            for p in profiles:
                ssid = str(getattr(p, "ssid", "") or "").strip()
                if not ssid:
                    continue
                connected = bool(getattr(info, "connected", False) and getattr(info, "ssid", None) == ssid)
                signal = None
                for n in networks:
                    if str(getattr(n, "ssid", "") or "").strip() == ssid:
                        signal = getattr(n, "signal_percent", None)
                        break
                text = ssid + ("  ✓ Connected" if connected else "")
                btn = self._make_button(text, lambda s=ssid, sec=getattr(p, "secure", None), c=connected, sig=signal: _open_profile_detail(s, sec, c, sig))
                profiles_layout.addWidget(btn)

            _clear_layout(nets_layout)
            if not networks:
                nets_layout.addWidget(QLabel("No networks found"))
            for n in networks:
                ssid = str(getattr(n, "ssid", "") or "").strip()
                if not ssid:
                    continue
                connected = bool(getattr(n, "is_connected", False))
                signal = getattr(n, "signal_percent", None)
                suffix = f" ({int(signal)}%)" if signal is not None else ""
                text = ssid + suffix + ("  ✓ Connected" if connected else "")
                nets_layout.addWidget(
                    self._make_button(
                        text,
                        lambda s=ssid, sec=getattr(n, "secure", None), c=connected, sig=signal: _open_profile_detail(s, sec, c, sig),
                    )
                )

        def _add_profile() -> None:
            ssid = str(add_ssid.text() or "").strip()
            pwd = str(add_pwd.text() or "")
            if not ssid:
                _notify("Enter an SSID")
                return
            add_fn = _host_or_module("add_wifi_profile", add_wifi_profile)
            ok = bool(add_fn(ssid, password=(pwd or None), secure=(True if pwd else None)))
            _notify("Profile added" if ok else "Add failed")
            if ok:
                add_ssid.clear()
                add_pwd.clear()
                _refresh_wifi()

        add_btn.clicked.connect(_add_profile)
        refresh_btn.clicked.connect(_refresh_wifi)

        _refresh_wifi()

        l.addStretch(1)
        stack.addWidget(list_page)
        stack.addWidget(detail)

        return page

    def _make_connectivity_bluetooth(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Bluetooth", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("section.connectivity"))
        root.addWidget(header)

        stack = QStackedWidget()
        root.addWidget(stack, 1)

        list_page = QWidget()
        l = QVBoxLayout(list_page)
        l.setContentsMargins(16, 12, 16, 16)
        l.setSpacing(10)
        l.addWidget(self._make_checkbox("Bluetooth Enabled", True))
        l.addWidget(SubHeading("Connected Device"))
        l.addWidget(QLabel("Pixel Buds Pro ✓"))
        l.addWidget(SubHeading("Available Devices"))

        detail = QWidget()
        d = QVBoxLayout(detail)
        d.setContentsMargins(16, 12, 16, 16)
        d.setSpacing(10)

        def open_device(name: str):
            while d.count() > 0:
                item = d.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            d.addWidget(SubHeading(name))
            d.addWidget(InfoRow("Status:", "Not Connected"))
            d.addWidget(InfoRow("Type:", "Audio Device"))
            d.addWidget(InfoRow("Battery:", "Unknown"))
            d.addWidget(self._make_button("Pair", lambda: stack.setCurrentWidget(list_page)))
            d.addWidget(self._make_button("Back", lambda: stack.setCurrentWidget(list_page)))
            d.addStretch(1)
            stack.setCurrentWidget(detail)

        for dev in ["Car Audio", "Keyboard-BT", "Speaker Mini"]:
            l.addWidget(self._make_button(dev, lambda s=dev: open_device(s)))

        l.addStretch(1)
        stack.addWidget(list_page)
        stack.addWidget(detail)
        return page

    def _make_connectivity_cellular(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Cellular"))
            self._add_info_rows(c, [
                ("Carrier", "Fictional Mobile LTE"),
                ("Signal Strength", "••••• (Strong)"),
                ("Network Type", "4G LTE"),
            ])
            c.addWidget(self._make_checkbox("Mobile Data Enabled", True))
            c.addWidget(self._make_checkbox("Data Roaming", False))

        p = SimpleTestPage("Cellular", build)
        p.backRequested.connect(lambda: self._go("section.connectivity"))
        return p

    def _make_connectivity_tethering(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(self._make_checkbox("Mobile Hotspot Enabled", False))
            c.addWidget(SubHeading("Hotspot Details"))
            ssid = "PixelProwler-Phone"
            password = "password123"
            if self.host_window is not None and hasattr(self.host_window, "config"):
                ssid = getattr(self.host_window.config, "hotspot_ssid", ssid)
                password = getattr(self.host_window.config, "hotspot_password", password)

            self._add_info_rows(c, [
                ("Hotspot Name", ssid),
                ("Password", password),
                ("Security", "WPA2-Personal"),
            ])
            c.addWidget(self._make_button("Change Hotspot Name"))
            c.addWidget(self._make_button("Change Password"))
            c.addWidget(SubHeading("Connected Devices"))
            c.addWidget(InfoRow("Status:", "0 devices connected"))
            c.addWidget(SubHeading("Data Usage"))
            c.addWidget(InfoRow("Session:", "0 MB"))
            c.addWidget(InfoRow("Monthly:", "0.0 GB"))

        p = SimpleTestPage("Tethering & Mobile Hotspot", build)
        p.backRequested.connect(lambda: self._go("section.connectivity"))
        return p

    def _make_personalization_appearance(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            initial_dark = False
            if self.host_window is not None and hasattr(self.host_window, "config"):
                initial_dark = bool(getattr(self.host_window.config, "dark_mode", False))
            dark = self._make_checkbox("Dark mode", initial_dark)

            if self.host_window is not None and hasattr(self.host_window, "set_setting"):
                dark.toggled.connect(lambda checked: self.host_window.set_setting("dark_mode", bool(checked)))

            c.addWidget(dark)

        p = SimpleTestPage("Appearance", build)
        p.backRequested.connect(lambda: self._go("section.personalization"))
        return p

    def _pick_wallpaper(self, key: str, instruction: str) -> Optional[str]:
        if self.host_window is None:
            return None
        picker = getattr(self.host_window, "request_photo", None)
        if not callable(picker):
            return None
        path = picker(title="Select Photo", instruction=instruction)
        if not path:
            return None
        if hasattr(self.host_window, "set_setting"):
            self.host_window.set_setting(key, str(path))
        return str(path)

    def _clear_wallpaper(self, key: str) -> None:
        if self.host_window is not None and hasattr(self.host_window, "set_setting"):
            self.host_window.set_setting(key, "")

    def _make_personalization_wallpaper(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Wallpaper", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("section.personalization"))
        root.addWidget(header)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 16)
        c.setSpacing(10)

        lock_label = QLabel()
        home_label = QLabel()
        lock_label.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
        home_label.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")

        def refresh_labels() -> None:
            lock = ""
            home = ""
            if self.host_window is not None and hasattr(self.host_window, "config"):
                lock = getattr(self.host_window.config, "lock_wallpaper", "") or ""
                home = getattr(self.host_window.config, "home_wallpaper", "") or ""
            lock_label.setText(f"Lock Screen: {Path(lock).name if lock else '(none)'}")
            home_label.setText(f"Home Screen: {Path(home).name if home else '(none)'}")

        c.addWidget(lock_label)
        c.addWidget(self._make_button("Set Lock Wallpaper", lambda: (self._pick_wallpaper("lock_wallpaper", "Select lock wallpaper"), refresh_labels())))
        c.addWidget(self._make_button("Clear Lock Wallpaper", lambda: (self._clear_wallpaper("lock_wallpaper"), refresh_labels())))
        c.addWidget(Divider())
        c.addWidget(home_label)
        c.addWidget(self._make_button("Set Home Wallpaper", lambda: (self._pick_wallpaper("home_wallpaper", "Select home wallpaper"), refresh_labels())))
        c.addWidget(self._make_button("Clear Home Wallpaper", lambda: (self._clear_wallpaper("home_wallpaper"), refresh_labels())))
        c.addStretch(1)

        refresh_labels()
        root.addWidget(content, 1)
        return page

    def _make_system_display(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Brightness"))
            c.addWidget(self._make_slider(50))
            c.addWidget(self._make_checkbox("Auto-Brightness", True))

        p = SimpleTestPage("Display", build)
        p.backRequested.connect(lambda: self._go("section.system"))
        return p

    def _make_system_datetime(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            auto_time = self._make_checkbox("Set time automatically", True)
            auto_date = self._make_checkbox("Set date automatically", True)
            c.addWidget(auto_time)
            c.addWidget(auto_date)

            c.addWidget(SubHeading("Formats"))
            use_24h = False
            if self.host_window is not None and hasattr(self.host_window, "config"):
                use_24h = bool(getattr(self.host_window.config, "use_24h_time", False))

            t24 = self._make_checkbox("Use 24-hour format", use_24h)
            if self.host_window is not None and hasattr(self.host_window, "set_setting"):
                t24.toggled.connect(lambda checked: self.host_window.set_setting("use_24h_time", bool(checked)))
            c.addWidget(t24)
            c.addWidget(self._make_checkbox("Show seconds on clock", False))

            c.addWidget(SubHeading("Manual Date & Time"))
            note = QLabel("(Disabled if automatic is on)")
            note.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")
            c.addWidget(note)

            date_picker = QDateEdit()
            date_picker.setDate(QDate.currentDate())
            date_picker.setCalendarPopup(True)
            date_picker.setEnabled(False)
            c.addWidget(date_picker)

            time_picker = QTimeEdit()
            time_picker.setTime(QTime.currentTime())
            time_picker.setDisplayFormat("HH:mm:ss" if t24.isChecked() else "hh:mm:ss AP")
            time_picker.setEnabled(False)
            c.addWidget(time_picker)

            def update_manual() -> None:
                enabled = not auto_time.isChecked() and not auto_date.isChecked()
                date_picker.setEnabled(enabled)
                time_picker.setEnabled(enabled)

            def update_format(checked: bool) -> None:
                time_picker.setDisplayFormat("HH:mm:ss" if checked else "hh:mm:ss AP")

            auto_time.toggled.connect(lambda _: update_manual())
            auto_date.toggled.connect(lambda _: update_manual())
            t24.toggled.connect(update_format)

        p = SimpleTestPage("Date & Time", build)
        p.backRequested.connect(lambda: self._go("section.time_and_language"))
        return p

    def _make_system_timeformat(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            use_24h = False
            if self.host_window is not None and hasattr(self.host_window, "config"):
                use_24h = bool(getattr(self.host_window.config, "use_24h_time", False))

            t24 = self._make_checkbox("Use 24-hour time", use_24h)
            if self.host_window is not None and hasattr(self.host_window, "set_setting"):
                t24.toggled.connect(lambda checked: self.host_window.set_setting("use_24h_time", bool(checked)))
            c.addWidget(t24)

        p = SimpleTestPage("Time Format", build)
        p.backRequested.connect(lambda: self._go("section.time_and_language"))
        return p

    def _make_system_audio(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Volume"))
            c.addWidget(self._make_slider(50))
            c.addWidget(self._make_checkbox("Vibration Enabled", True))
            c.addWidget(self._make_button("Ringtone (Default)"))

        p = SimpleTestPage("Audio", build)
        p.backRequested.connect(lambda: self._go("section.system"))
        return p

    def _make_system_developer(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(self._make_checkbox("USB Debugging", False))
            c.addWidget(self._make_checkbox("Show Visual Touches", False))
            c.addWidget(self._make_checkbox("Force GPU Rendering", True))

        p = SimpleTestPage("Developer Options", build)
        p.backRequested.connect(lambda: self._go("section.update"))
        return p

    def _make_system_reset(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(self._make_button("Reset Network Settings"))
            c.addWidget(self._make_button("Reset All Settings"))
            c.addWidget(self._make_button("Erase All Data (Factory Reset)"))

        p = SimpleTestPage("Reset Options", build)
        p.backRequested.connect(lambda: self._go("section.update"))
        return p

    def _make_system_battery(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Battery", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("section.system"))
        root.addWidget(header)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 16)
        c.setSpacing(10)

        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(8)
        c.addLayout(rows_layout)

        def refresh_info() -> None:
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            info = get_battery_info()
            rows_layout.addWidget(InfoRow("Battery:", self._fmt_int(info.percentage, "%") or "-"))
            rows_layout.addWidget(InfoRow("Charging:", "Yes" if info.is_charging else "No"))
            rows_layout.addWidget(InfoRow("Voltage:", self._fmt_float(info.voltage, "V") or "-"))
            rows_layout.addWidget(InfoRow("Current:", self._fmt_float(info.current, "A") or "-"))
            rows_layout.addWidget(InfoRow("Power:", self._fmt_float(info.power, "W") or "-"))

        c.addWidget(self._make_button("Battery Health", lambda: self._go("system.battery_health")))
        c.addWidget(self._make_button("Refresh", refresh_info))
        c.addStretch(1)
        refresh_info()

        root.addWidget(content, 1)
        return page

    def _make_system_battery_health(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Battery Health", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("system.battery"))
        root.addWidget(header)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 16)
        c.setSpacing(10)

        warning = QLabel()
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
        c.addWidget(warning)

        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(8)
        c.addLayout(rows_layout)

        def refresh_info() -> None:
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            info = get_battery_info()
            health = info.health_percentage
            msg = ""
            if health is not None:
                if health < 50:
                    msg = "Your battery can no longer hold a useful charge. Get it replaced by a Grizzco repair center as soon as possible."
                elif health < 80:
                    msg = "Your battery has degraded. Consider getting it replaced at a Grizzco repair center."

            warning.setVisible(bool(msg))
            warning.setText(f"<b>Important Battery Message</b><br>{msg}" if msg else "")

            rows_layout.addWidget(InfoRow("Battery Health:", self._fmt_float(health, "%", 1) or "-"))
            rows_layout.addWidget(InfoRow("Design Capacity:", self._fmt_float(info.design_capacity, "mWh", 0) or "-"))
            rows_layout.addWidget(InfoRow("Full Charge Capacity:", self._fmt_float(info.full_charge_capacity, "mWh", 0) or "-"))
            rows_layout.addWidget(InfoRow("Cycle Count:", self._fmt_int(info.cycle_count) or "-"))

        c.addWidget(self._make_button("Refresh", refresh_info))
        c.addStretch(1)
        refresh_info()

        root.addWidget(content, 1)
        return page

    def _make_system_about(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("About", show_back=True, left_icon=None)
        header.backClicked.connect(lambda: self._go("section.system"))
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 12, 16, 20)
        c.setSpacing(8)

        os_cfg = OSBuildConfigStore().load()
        dev_cfg = DeviceConfigStore().load()

        os_name = getattr(os_cfg, "os_name", "")
        os_version = getattr(os_cfg, "os_version", "")
        os_display = " ".join(part for part in [os_name, os_version] if part)
        builder_user = getattr(os_cfg, "builder_username", "")
        builder_host = getattr(os_cfg, "builder_hostname", "")
        builder_display = ""

        if builder_user or builder_host:
            builder_display = f"{builder_user}@{builder_host}".strip("@")
        build_datetime = getattr(os_cfg, "build_datetime", "")
        try:
            build_datetime = datetime.fromisoformat(build_datetime).strftime("%B %d, %Y %H:%M")
        except Exception:
            pass

                # --- Subheading ---
        if os_display:
            subheading = QLabel(os_display)
            subheading.setStyleSheet("font-size: 23px; font-weight: bold;")
            subheading.setWordWrap(True)
            c.addWidget(subheading)

            c.addSpacing(4)

        self._add_info_rows(c, [
            ("Build number", str(getattr(os_cfg, "build_number", ""))),
            ("Build ID", getattr(os_cfg, "build_id", "")),
            ("Channel", getattr(os_cfg, "channel", "")),
            ("Builder", builder_display),
            ("Build date", build_datetime),
        ])

        c.addWidget(Divider())

        self._add_info_rows(c, [
            ("Manufacturer", getattr(dev_cfg, "manufacturer", "")),
            ("Model", f"{getattr(dev_cfg, 'model', '')} ({getattr(dev_cfg, 'model_name', '')})"),
            ("Serial Number", getattr(dev_cfg, "serial_number", "")),
            ("Hardware Revision", getattr(dev_cfg, "hardware_revision", "")),
        #    ("IMEI", getattr(dev_cfg, "imei", "")),
        #    ("WiFi MAC", getattr(dev_cfg, "wifi_mac", "")),
        #    ("Bluetooth MAC", getattr(dev_cfg, "bluetooth_mac", "")),
        ])

        c.addItem(QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        return page

    def _make_update_check(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Check for updates"))
            c.addWidget(QLabel("Your device is up to date."))
            c.addWidget(self._make_button("Check now"))
            c.addWidget(Divider())
            c.addWidget(SubHeading("Update history"))
            c.addWidget(QLabel("No updates installed."))

        p = SimpleTestPage("Check for updates", build)
        p.backRequested.connect(lambda: self._go("section.update"))
        return p

    def _make_update_security(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Security"))
            c.addWidget(self._make_checkbox("Enable device encryption", True))
            c.addWidget(self._make_checkbox("Automatic backups", False))
            c.addWidget(Divider())
            c.addWidget(self._make_button("Recovery options"))

        p = SimpleTestPage("Security", build)
        p.backRequested.connect(lambda: self._go("section.update"))
        return p

    # ----- test page builders -----

    def _make_test_buttons(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("buttons"))
            b1 = QPushButton("primary-ish")
            b1.setFixedHeight(40)
            b1.setCursor(Qt.PointingHandCursor)
            b1.setStyleSheet(
                f"""
                QPushButton {{
                    background: {qcolor_css(PANEL2)};
                    border: 1px solid {qcolor_css(ACCENT)};
                    color: {qcolor_css(TEXT)};
                    border-radius: 2px;
                    padding: 6px 12px;
                    font-size: 14px;
                }}
                QPushButton:hover {{ border: 1px solid {qcolor_css(TEXT)}; }}
                QPushButton:pressed {{ background: {qcolor_css(PANEL)}; }}
                """
            )
            c.addWidget(b1)

            b2 = QPushButton("neutral")
            b2.setFixedHeight(40)
            b2.setCursor(Qt.PointingHandCursor)
            b2.setStyleSheet(
                f"""
                QPushButton {{
                    background: {qcolor_css(PANEL2)};
                    border: 1px solid {qcolor_css(DIVIDER)};
                    color: {qcolor_css(TEXT)};
                    border-radius: 2px;
                    padding: 6px 12px;
                    font-size: 14px;
                }}
                QPushButton:hover {{ border: 1px solid {qcolor_css(MUTED)}; }}
                """
            )
            c.addWidget(b2)

            c.addWidget(Divider())
            c.addWidget(SubHeading("nav rows"))
            sample = NavRowItem("Example row", "subtitle goes here", make_glyph_icon(GLYPH_SYSTEM, 18, ACCENT))
            c.addWidget(sample)

        p = SimpleTestPage("Buttons", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_text(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("text input"))
            le = QLineEdit()
            le.setPlaceholderText("type something")
            le.setClearButtonEnabled(True)
            le.setFixedHeight(36)
            le.setStyleSheet(
                f"""
                QLineEdit {{
                    background: transparent;
                    border: 1px solid {qcolor_css(MUTED)};
                    border-radius: 2px;
                    padding: 6px 10px;
                    color: {qcolor_css(TEXT)};
                    font-size: 14px;
                }}
                QLineEdit:focus {{
                    border: 1px solid {qcolor_css(ACCENT)};
                }}
                """
            )
            c.addWidget(le)

            c.addWidget(SubHeading("labels"))
            l1 = QLabel("normal text")
            l1.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
            l2 = QLabel("muted text")
            l2.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")
            c.addWidget(l1)
            c.addWidget(l2)

        p = SimpleTestPage("Text input", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_lists(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("list rows"))
            wrap = QFrame()
            v = QVBoxLayout(wrap)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)

            for i in range(1, 6):
                v.addWidget(NavRowItem(f"Row {i}", "tap target + chevron", None))
                v.addWidget(Divider())

            c.addWidget(wrap)

        p = SimpleTestPage("Lists", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_misc(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("headings + info rows"))
            c.addWidget(InfoRow("Label:", "Value"))
            c.addWidget(InfoRow("Long label:", "A longer value that wraps onto the next line if needed."))
            c.addWidget(Divider())
            c.addWidget(SubHeading("spacing"))
            t = QLabel("this page is just here to eyeball spacing + typography.")
            t.setWordWrap(True)
            t.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
            c.addWidget(t)

        p = SimpleTestPage("Misc", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p


class App:
    """
    Compatibility wrapper for the phoneos app system.

    Usage: App(window, container)
    Creates the settings UI inside the provided `container` widget so the
    platform can host the app in its own window/layout (matching `main-old.py`).
    """
    def __init__(self, window, container):
        self.window = window
        self.container = container

        # Create the SettingsWindow (keeps internal page widget structure)
        self._window = SettingsWindow(self.window)

        # Host the stacked widget inside the provided container
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        container.setLayout(layout)

        # Reparent the stack widget into the container and show it
        self._window.stack.setParent(container)
        layout.addWidget(self._window.stack)

def main() -> int:
    app = QApplication(sys.argv)

    w = SettingsWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
