# win10m_settings_mock.py
# PySide6 recreation (lightweight) of the Windows 10 Mobile Settings app shell.
# Windows 11 23H2 target. No extra deps besides PySide6.

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from deletescapeui import (
    ACCENT,
    DIVIDER,
    MUTED,
    PANEL,
    PANEL2,
    TEXT,
    Divider,
    GLYPH_GEAR,
    GLYPH_NETWORK,
    GLYPH_SYSTEM,
    GLYPH_TEST,
    HeaderBar,
    InWindowDialog,
    InfoRow,
    NavRowItem,
    SubHeading,
    line_edit_stylesheet,
    make_glyph_icon,
    neutral_button_stylesheet,
    primary_button_stylesheet,
    qcolor_css,
    styled_combo_box,
    styled_progress_bar,
    styled_radio_button,
    styled_slider,
    styled_spin_box,
    styled_button,
    styled_line_edit,
    styled_switch,
    styled_text_area,
)


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

        header = HeaderBar("DeletescapeUI Sample", show_back=False, left_icon=make_glyph_icon(GLYPH_GEAR, 18, ACCENT))
        root.addWidget(header)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 6, 16, 16)
        body_l.setSpacing(12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a setting")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(36)
        self.search.setStyleSheet(line_edit_stylesheet())
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
        search.setStyleSheet(line_edit_stylesheet())
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
        search.setStyleSheet(line_edit_stylesheet())
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

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(16, 5, 16, 20)
        c.setSpacing(12)

        build_body(c)
        root.addWidget(content, 1)


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
            ("samples", "Samples", "Mock app screens using controls", make_glyph_icon(GLYPH_SYSTEM, 18, ACCENT)),
            ("test", "Test", "Control test pages", make_glyph_icon(GLYPH_TEST, 18, ACCENT)),
        ]
        hub = HubPage(sections)
        hub.navigateToSection.connect(self._open_section)
        self._add_page("hub", hub)

        sample_index_pages = [
            ("samples.weather", "Weather", "Forecast home mockup", make_glyph_icon(GLYPH_NETWORK, 18, ACCENT)),
            ("samples.music", "Music", "Now playing mockup", make_glyph_icon(GLYPH_SYSTEM, 18, ACCENT)),
            ("samples.messaging", "Inbox", "Inbox mockup", make_glyph_icon(GLYPH_GEAR, 18, ACCENT)),
        ]
        sample_index = SectionIndexPage("Samples", [("samples.home", "All samples", "", None)])
        sample_index.backToHub.connect(lambda: self._go("hub"))
        sample_index.navigateToPage.connect(self._go)
        self._add_page("section.samples", sample_index)

        samples_home = TestHomePage(sample_index_pages, title="Samples")
        samples_home.backRequested.connect(lambda: self._go("hub"))
        samples_home.openTestPage.connect(self._go)
        self._add_page("samples.home", samples_home)
        
        test_index_pages = [
            ("test.buttons", "Buttons", "Push buttons, tool buttons", None),
            ("test.text", "Text input", "Line edits, placeholder, clear button", None),
            ("test.textarea", "Text area", "Multiline text input", None),
            ("test.selection", "Selection", "Combo box, radio, switches", None),
            ("test.range", "Range", "Sliders, progress, spin boxes", None),
            ("test.dialogs", "Dialogs", "In-window custom dialogs", None),
            ("test.lists", "Lists", "List rows, separators", None),
            ("test.misc", "Misc", "Spacing, headings, dividers", None),
        ]
        test_index = SectionIndexPage("Test", [("test.home", "All test pages", "", None)])
        test_index.backToHub.connect(lambda: self._go("hub"))
        test_index.navigateToPage.connect(self._go)
        self._add_page("section.test", test_index)
        
        # Test home
        test_home = TestHomePage(test_index_pages)
        test_home.backRequested.connect(lambda: self._go("hub"))
        test_home.openTestPage.connect(self._go)
        self._add_page("test.home", test_home)

        # Test pages
        self._add_page("test.buttons", self._make_test_buttons())
        self._add_page("test.text", self._make_test_text())
        self._add_page("test.textarea", self._make_test_textarea())
        self._add_page("test.selection", self._make_test_selection())
        self._add_page("test.range", self._make_test_range())
        self._add_page("test.dialogs", self._make_test_dialogs())
        self._add_page("test.lists", self._make_test_lists())
        self._add_page("test.misc", self._make_test_misc())

        # Sample app mockups
        self._add_page("samples.weather", self._make_sample_weather())
        self._add_page("samples.weather.details", self._make_sample_weather_details())
        self._add_page("samples.music", self._make_sample_music())
        self._add_page("samples.music.devices", self._make_sample_music_devices())
        self._add_page("samples.messaging", self._make_sample_messaging())
        self._add_page("samples.messaging.compose", self._make_sample_messaging_compose())

        self._go("samples.weather.details")
        
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
        elif section_key == "samples":
            self._go("samples.home")
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

    def _dialog_host(self) -> QWidget:
        current = self.stack.currentWidget()
        if current is not None and current.isVisible():
            return current

        stack_parent = self.stack.parentWidget()
        if stack_parent is not None and stack_parent.isVisible():
            return stack_parent

        stack_window = self.stack.window()
        if stack_window is not None and stack_window.isVisible():
            return stack_window

        return self

    def _make_button(self, text: str, on_click: Optional[Callable[[], None]] = None) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(38)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(neutral_button_stylesheet())
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

    # ----- test page builders -----

    def _make_test_buttons(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("buttons"))
            b1 = QPushButton("primary-ish")
            b1.setFixedHeight(40)
            b1.setCursor(Qt.PointingHandCursor)
            b1.setStyleSheet(primary_button_stylesheet())
            c.addWidget(b1)

            b2 = QPushButton("neutral")
            b2.setFixedHeight(40)
            b2.setCursor(Qt.PointingHandCursor)
            b2.setStyleSheet(neutral_button_stylesheet())
            c.addWidget(b2)

            c.addWidget(Divider())
            c.addWidget(SubHeading("nav rows"))
            sample = NavRowItem("Example row", "Subtitle goes here", make_glyph_icon(GLYPH_SYSTEM, 18, ACCENT))
            c.addWidget(sample)

        p = SimpleTestPage("Buttons", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_text(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Text input"))
            le = QLineEdit()
            le.setPlaceholderText("Type something")
            le.setClearButtonEnabled(True)
            le.setFixedHeight(36)
            le.setStyleSheet(line_edit_stylesheet())
            c.addWidget(le)

            c.addWidget(SubHeading("Labels"))
            l1 = QLabel("Normal text")
            l1.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
            l2 = QLabel("Muted text")
            l2.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")
            c.addWidget(l1)
            c.addWidget(l2)

        p = SimpleTestPage("Text input", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_lists(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("List rows"))
            wrap = QFrame()
            v = QVBoxLayout(wrap)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)

            for i in range(1, 6):
                v.addWidget(NavRowItem(f"Row {i}", "Tap target + chevron", None))
                v.addWidget(Divider())

            c.addWidget(wrap)

        p = SimpleTestPage("Lists", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_textarea(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Multiline input"))
            ta = styled_text_area("Type multiple lines")
            c.addWidget(ta)

            c.addWidget(SubHeading("Filled state"))
            filled = styled_text_area()
            filled.setPlainText("line 1\nline 2\nline 3")
            c.addWidget(filled)

        p = SimpleTestPage("Text area", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_selection(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Combo box"))
            combo = styled_combo_box(["Option A", "Option B", "Option C"])
            c.addWidget(combo)

            c.addWidget(SubHeading("Radio buttons"))
            c.addWidget(styled_radio_button("Choice one", checked=True))
            c.addWidget(styled_radio_button("Choice two"))

            c.addWidget(SubHeading("Switches"))
            c.addWidget(styled_switch("Wi-Fi", checked=True))
            c.addWidget(styled_switch("Bluetooth", checked=False))

        p = SimpleTestPage("Selection", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_range(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Slider + progress"))
            progress = styled_progress_bar(value=40)
            progress_notext = styled_progress_bar(value=40, show_text=False)
            slider = styled_slider(value=40)
            slider.valueChanged.connect(progress.setValue)
            c.addWidget(progress)
            c.addWidget(progress_notext)
            c.addWidget(slider)

            c.addWidget(SubHeading("Spin box"))
            spin = styled_spin_box(value=12, minimum=0, maximum=100)
            spin.valueChanged.connect(progress.setValue)
            c.addWidget(spin)

        p = SimpleTestPage("Range", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_misc(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Headings + info rows"))
            c.addWidget(InfoRow("Label:", "Value"))
            c.addWidget(InfoRow("Long label:", "A longer value that wraps onto the next line if needed."))
            c.addWidget(Divider())
            c.addWidget(SubHeading("spacing"))
            t = QLabel("This page is just here to eyeball spacing + typography.")
            t.setWordWrap(True)
            t.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
            c.addWidget(t)

        p = SimpleTestPage("Misc", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_test_dialogs(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("in-window dialogs"))

            result = QLabel("Last action: none")
            result.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 13px;")
            c.addWidget(result)

            open_basic = styled_button("Open basic dialog", primary=True)
            c.addWidget(open_basic)

            open_custom = styled_button("Open dialog with custom body")
            c.addWidget(open_custom)

            def launch_basic() -> None:
                dlg = InWindowDialog(
                    self._dialog_host(),
                    title="Confirm Action",
                    message="Apply this setting change now?",
                    confirm_text="Apply",
                    cancel_text="Cancel",
                )
                dlg.accepted.connect(lambda: result.setText("Last action: applied"))
                dlg.rejected.connect(lambda: result.setText("Last action: canceled"))
                dlg.open()

            def launch_custom() -> None:
                body = QWidget()
                b = QVBoxLayout(body)
                b.setContentsMargins(0, 0, 0, 0)
                b.setSpacing(8)

                hint = QLabel("Type DELETE to confirm")
                hint.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")
                entry = styled_line_edit("DELETE")
                b.addWidget(hint)
                b.addWidget(entry)

                dlg = InWindowDialog(
                    self._dialog_host(),
                    title="Delete profile",
                    message="This action cannot be undone.",
                    confirm_text="Delete",
                    cancel_text="Keep",
                )
                dlg.set_body(body)

                def on_accept() -> None:
                    valid = entry.text().strip().upper() == "DELETE"
                    result.setText("Last action: deleted" if valid else "Last action: validation failed")

                dlg.accepted.connect(on_accept)
                dlg.rejected.connect(lambda: result.setText("Last action: kept"))
                dlg.open()

            open_basic.clicked.connect(launch_basic)
            open_custom.clicked.connect(launch_custom)

        p = SimpleTestPage("Dialogs", build)
        p.backRequested.connect(lambda: self._go("test.home"))
        return p

    def _make_sample_weather(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            city = QLabel("Seattle")
            city.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 14px;")
            c.addWidget(city)

            temp = QLabel("18°")
            temp.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 56px; font-weight: 600;")
            c.addWidget(temp)

            condition = QLabel("Cloudy")
            condition.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 22px; font-weight: 600;")
            c.addWidget(condition)

            c.addWidget(Divider())
            
            c.addWidget(InfoRow("High", "21°"))
            c.addWidget(InfoRow("Rain", "35%"))

            open_details = styled_button("View hourly forecast", primary=True)
            open_details.clicked.connect(lambda: self._go("samples.weather.details"))
            c.addWidget(open_details)

        p = SimpleTestPage("Weather", build)
        p.backRequested.connect(lambda: self._go("samples.home"))
        return p

    def _make_sample_weather_details(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("next hours"))
            c.addWidget(InfoRow("09:00", "15° | Cloudy"))
            c.addWidget(InfoRow("12:00", "18° | Light rain"))
            c.addWidget(InfoRow("15:00", "20° | Cloudy"))
            c.addWidget(InfoRow("18:00", "17° | Clear"))

            c.addWidget(SubHeading("Alerts"))
            c.addWidget(styled_switch("Severe weather alerts", checked=True))

            c.addWidget(SubHeading("Units"))
            c.addWidget(styled_radio_button("Celsius", checked=True))
            c.addWidget(styled_radio_button("Fahrenheit"))

        p = SimpleTestPage("Hourly Forecast", build)
        p.backRequested.connect(lambda: self._go("samples.weather"))
        return p

    def _make_sample_weather_details(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)   # <- remove outer margins
            layout.setSpacing(0)                    # <- remove spacing between widgets
            c.addLayout(layout)

            self.web = QWebEngineView()
            self.web.setContentsMargins(0, 0, 0, 0) # <- ensure the widget has no padding
            layout.addWidget(self.web)

            # ---- Mobile user agent ----
            self.web.page().profile().setHttpUserAgent(
                "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/142.0.0.0 Mobile Safari/537.36"
            )


            self.web.setUrl(QUrl("https:/captive.apple.com"))

        def launch_dialog() -> None:
            # FIXME: #4 (grammar)
            dlg = InWindowDialog(
                self._dialog_host(),
                title="No internet connection",
                message="If you didn't complete the captive portal, no internet will occur.",
                confirm_text="Apply",
                cancel_text="Cancel",
            )
            dlg.accepted.connect(lambda: self.window.launch_app("home"))
            dlg.open()

        p = SimpleTestPage("Sign in to network", build)
        # TODO: Make this smart, run conntests in the bg and if one succeeds, don't show dialog
        p.backRequested.connect(lambda: launch_dialog())
        return p

    def _make_sample_music(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(InfoRow("Track:", "Northern Lights"))
            c.addWidget(InfoRow("Artist:", "Deletescape Collective"))
            
            scrub = styled_slider(value=42)
            c.addWidget(scrub)

            controls = QHBoxLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(8)
            controls.addWidget(styled_button("Previous"))
            controls.addWidget(styled_button("Pause", primary=True))
            controls.addWidget(styled_button("Next"))
            c.addLayout(controls)

            open_devices = styled_button("Audio & playback settings")
            open_devices.clicked.connect(lambda: self._go("samples.music.devices"))
            c.addWidget(open_devices)

        p = SimpleTestPage("Music", build)
        p.backRequested.connect(lambda: self._go("samples.home"))
        return p

    def _make_sample_music_devices(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Output device"))
            c.addWidget(styled_combo_box(["Phone speaker", "Bluetooth headset", "Car audio"]))

            c.addWidget(SubHeading("Volume"))
            vol_slider = styled_slider(value=70)
            c.addWidget(vol_slider)

            c.addWidget(SubHeading("Playback"))
            c.addWidget(styled_switch("Shuffle", checked=True))
            c.addWidget(styled_switch("Crossfade", checked=False))

        p = SimpleTestPage("Playback Settings", build)
        p.backRequested.connect(lambda: self._go("samples.music"))
        return p

    def _make_sample_messaging(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            c.addWidget(SubHeading("Recently contacted"))
            chat_list = QFrame()
            chat_list.setStyleSheet(
                f"""
                QFrame {{
                    background: {qcolor_css(PANEL)};
                    border: 1px solid {qcolor_css(DIVIDER)};
                    border-radius: 4px;
                }}
                """
            )
            chat_l = QVBoxLayout(chat_list)
            chat_l.setContentsMargins(0, 0, 0, 0)
            chat_l.setSpacing(0)
            chat_l.addWidget(NavRowItem("Ari", "See you at 7?", None))
            chat_l.addWidget(Divider())
            chat_l.addWidget(NavRowItem("Design Team", "Mock approved", None))
            c.addWidget(chat_list)

            compose_btn = styled_button("Compose new mail", primary=True)
            compose_btn.clicked.connect(lambda: self._go("samples.messaging.compose"))
            c.addWidget(compose_btn)

        p = SimpleTestPage("Messaging", build)
        p.backRequested.connect(lambda: self._go("samples.home"))
        return p

    def _make_sample_messaging_compose(self) -> QWidget:
        def build(c: QVBoxLayout) -> None:
            recipient = styled_line_edit("Recipient")
            message = styled_text_area("Write your mail")
            c.addWidget(recipient)
            c.addWidget(message)

            schedule = styled_switch("Schedule send", checked=False)
            c.addWidget(schedule)

            status = QLabel("Status: idle")
            status.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 13px;")

            actions = QHBoxLayout()
            actions.setContentsMargins(0, 0, 0, 0)
            actions.setSpacing(8)
            preview = styled_button("Preview")
            send = styled_button("Send", primary=True)
            actions.addWidget(preview)
            actions.addWidget(send)
            c.addLayout(actions)
            c.addWidget(status)

            def show_preview() -> None:
                body = QWidget()
                b = QVBoxLayout(body)
                b.setContentsMargins(0, 0, 0, 0)
                b.setSpacing(6)
                b.addWidget(InfoRow("To:", recipient.text().strip() or "(none)"))
                b.addWidget(InfoRow("Message:", message.toPlainText().strip() or "(empty)"))
                b.addWidget(InfoRow("Scheduled:", "Yes" if schedule.isChecked() else "No"))

                dlg = InWindowDialog(self._dialog_host(), title="Message preview", message="Review before sending", confirm_text="Send", cancel_text="Edit")
                dlg.set_body(body)
                dlg.accepted.connect(lambda: status.setText("Status: sent"))
                dlg.rejected.connect(lambda: status.setText("Status: draft"))
                dlg.open()

            def send_message() -> None:
                target = recipient.text().strip()
                text = message.toPlainText().strip()
                if not target or not text:
                    status.setText("Status: missing recipient or message")
                    return
                status.setText("Status: scheduled" if schedule.isChecked() else "Status: sent")

            preview.clicked.connect(show_preview)
            send.clicked.connect(send_message)

        p = SimpleTestPage("Compose", build)
        p.backRequested.connect(lambda: self._go("samples.messaging"))
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
