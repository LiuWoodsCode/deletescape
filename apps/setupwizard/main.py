from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from apps.setupwizard.deletescapeui import (
    ACCENT,
    MUTED,
    TEXT,
    GLYPH_SYSTEM,
    HeaderBar,
    apply_theme_for_current_scheme,
    make_glyph_icon,
    qcolor_css,
    styled_button,
    styled_checkbox,
    styled_combo_box,
    styled_switch,
    styled_text_area,
)
from wifi import get_wifi_info, scan_wifi_networks, list_wifi_profiles


class App:
    def __init__(self, window, container):
        apply_theme_for_current_scheme()
        self.window = window
        self.container = container

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.container.setLayout(self.layout)

        self._steps = [
            "beta_notice",
            "language_region",
            "license",
            "network",
            "time_format",
            "appearance",
            "welcome",
        ]
        self._step_index = 0

        self._language_combo: QComboBox | None = None
        self._region_combo: QComboBox | None = None
        self._network_choice: QComboBox | None = None
        self._license_accepted: QCheckBox | None = None

        self._render_step()

    def _clear_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _title(self, text: str) -> None:
        self._header(text)

    def _header(self, title: str) -> None:
        show_back = self._step_index > 0
        header = HeaderBar(
            title,
            show_back=show_back,
        )
        if show_back:
            header.backClicked.connect(self._prev_step)
        self.layout.addWidget(header)

    def _body_text(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 14px;")
        self.layout.addWidget(label)

    def _field_label(self, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 13px;")
        self.layout.addWidget(label)

    def _load_gplv3_text(self) -> str:
        candidates = [
            Path(__file__).with_name("gplv3.txt"),
            Path(__file__).resolve().parents[2] / "gplv3.txt",
        ]
        for path in candidates:
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8").strip()
                except OSError:
                    break
        raise "The system cannot find a license agreement in gplv3.txt and cannot legally continue."

    def _load_incsan_text(self) -> str:
        candidates = [
            Path(__file__).with_name("inclusivesans.txt"),
            Path(__file__).resolve().parents[2] / "inclusivesans.txt",
        ]
        for path in candidates:
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8").strip()
                except OSError:
                    break
        raise "The system cannot find a license agreement in inclusivesans.txt and cannot legally continue."
    
    def _add_expandable_section(self, title: str, text: str, *, expanded: bool = False) -> None:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(6)

        toggle = QPushButton()
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                color: {qcolor_css(TEXT)};
                border: 1px solid {qcolor_css(MUTED)};
                border-radius: 8px;
                padding: 8px 10px;
                background: transparent;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                border-color: {qcolor_css(ACCENT)};
            }}
            """
        )

        body: QPlainTextEdit = styled_text_area()
        body.setReadOnly(True)
        body.setPlainText(text)
        body.setVisible(expanded)
        body.setMinimumHeight(120)
        body.setMaximumHeight(220)

        def _sync_state(checked: bool) -> None:
            marker = "▼" if checked else "▶"
            toggle.setText(f"{marker} {title}")
            body.setVisible(checked)

        toggle.toggled.connect(_sync_state)
        _sync_state(expanded)

        section_layout.addWidget(toggle)
        section_layout.addWidget(body)
        self.layout.addWidget(section)

    def _nav_row(self, *, back_enabled: bool, next_text: str = "Next", next_enabled: bool = True, next_handler=None) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        back_btn = styled_button("Back")
        back_btn.setEnabled(back_enabled)
        back_btn.clicked.connect(self._prev_step)

        next_btn = styled_button(next_text, primary=True)
        next_btn.setEnabled(next_enabled)
        next_btn.clicked.connect(next_handler if callable(next_handler) else self._next_step)

        row_layout.addWidget(back_btn)
        row_layout.addStretch(1)
        row_layout.addWidget(next_btn)
        self.layout.addWidget(row)

    def _render_step(self) -> None:
        self._clear_layout()

        step = self._steps[self._step_index]
        if step == "beta_notice":
            self._title("Beta Notice")
            self._body_text(
                "You are using a developmental build of deletescapeOS. Features may be incomplete and stability is not guaranteed, and some security features are not available. If you did not expect to see this message, please follow your device's instructions for reinstalling a production version of deletescapeOS."
            )
            self.layout.addStretch(1)
            self._nav_row(back_enabled=False)
            return

        if step == "language_region":
            self._title("Language and Region")

            self._field_label("Language")
            self._language_combo = styled_combo_box()
            self._language_combo.addItems([
                "English",
                "Arr Matey",
                "kitten :3",
                "Similish",
                "01011010",
            ])
            self.layout.addWidget(self._language_combo)

            self._field_label("Country/Region")
            self._region_combo = styled_combo_box()
            self._region_combo.addItems([
                "United States",
                "Canada",
                "Inkopolis",
                "Colony 9",
            ])
            self.layout.addWidget(self._region_combo)

            self.layout.addStretch(1)
            self._nav_row(back_enabled=True)
            return

        if step == "network":
            self._title("Network Connectivity")

            def _host_or_module(name: str, fallback):
                fn = getattr(self.window, name, None)
                return fn if callable(fn) else fallback

            get_info = _host_or_module("get_wifi_info", get_wifi_info)
            scan = _host_or_module("scan_wifi_networks", scan_wifi_networks)
            list_profiles = _host_or_module("list_wifi_profiles", list_wifi_profiles)

            info = get_info()
            scanned = list(scan() or [])
            profiles = list(list_profiles() or [])

            driver_name = str(getattr(info, "driver", "unknown") or "unknown")
            connected_ssid = str(getattr(info, "ssid", "") or "").strip()

            network_names: list[str] = []
            seen: set[str] = set()

            if connected_ssid:
                network_names.append(connected_ssid)
                seen.add(connected_ssid.casefold())

            for n in scanned:
                ssid = str(getattr(n, "ssid", "") or "").strip()
                if not ssid:
                    continue
                key = ssid.casefold()
                if key in seen:
                    continue
                seen.add(key)
                network_names.append(ssid)

            for p in profiles:
                ssid = str(getattr(p, "ssid", "") or "").strip()
                if not ssid:
                    continue
                key = ssid.casefold()
                if key in seen:
                    continue
                seen.add(key)
                network_names.append(ssid)

            if not network_names:
                network_names = ["No networks found"]

            self._field_label("Available networks")
            self._network_choice = styled_combo_box()
            self._network_choice.addItems(network_names + ["Skip for now"])
            self.layout.addWidget(self._network_choice)

            self.layout.addStretch(1)
            self._nav_row(back_enabled=True)
            return

        if step == "license":
            self._title("License Agreement")

            self._body_text(
                "Review and expand each section below. You must read and accept the license to continue."
            )

            gpl_intro = (
                "This program is free software: you can redistribute it and/or modify it under the terms "
                "of the GNU General Public License as published by the Free Software Foundation, "
                "version 3 of the License.\n\n"
                "This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; "
                "without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. "
                "See the GNU General Public License below for more details."
            )

            team_salavo_text = (
                "This software makes reference to the video game Doki Doki Literature Club and certain "
                "characters originating from that work. Doki Doki Literature Club was created by Team "
                "Salvato, and all related intellectual property, including the game title and character "
                "names, remains the property of its respective copyright holder(s).\n\n"
                "The following names and characters may appear within this software:\n"
                "- Doki Doki Literature Club\n"
                "- Monika\n"
                "- Sayori\n"
                "- Natsuki\n"
                "- Yuri\n\n"
                "These references are included solely as homage and in good faith, with respect for the "
                "original work and its creators. Their inclusion is not intended to imply endorsement, "
                "partnership, or affiliation with Team Salvato.\n\n"
                "These names are used under goodwill, and are not used to market the software. The "
                "maintainers of this software do not claim ownership of these names or associated "
                "intellectual property and do not object to their removal. Should Team Salvato or an "
                "authorized legal representative request the removal of these references, such a request "
                "may be submitted to, and the maintainers will promptly review and remove the referenced "
                "material if requested."
            )

            maia_text = (
                "This software project contains references to the individual known as maia arson crimew, "
                "including names, aliases, and phrases that have become associated with public events and "
                "internet culture. These references are included as cultural and historical references only.\n\n"
                "The following names, identifiers, and phrases may appear within this software or its "
                "documentation:\n_load_gplv3_text"
                "- maia arson crimew\n"
                "- Tillie Kottmann\n"
                "- Tillie crimew\n"
                "- deletescape\n"
                "- deletescapeOS\n"
                "- holy fucking bingle\n\n"
                "The codename of this operating system, \"deletescape,\" may also appear in contexts "
                "referencing the same string used publicly by maia arson crimew. Public records indicate "
                "that the individual has used the names maia arson crimew, Tillie Kottmann, Tillie crimew, "
                "and the identifier deletescape.\n\n"
                "These references are included in good faith and for contextual or cultural reference "
                "purposes only. Their inclusion is not intended to imply endorsement, collaboration, "
                "approval, or affiliation with maia arson crimew.\n\n"
                "The maintainer of this software is not maia arson crimew and is not associated with maia "
                "arson crimew in any capacity.\n\n"
                "No claim of identity, representation, or connection is made with respect to maia arson "
                "crimew, the names listed above, or any actions historically attributed to that individual.\n\n"
                "These references are included under goodwill and as a matter of cultural reference. The "
                "maintainer of this software does not claim ownership of these names, identifiers, or "
                "phrases and does not object to their removal. If maia arson crimew or an authorized legal "
                "representative requests that these references be removed or modified, such a request may "
                "be submitted to <email>, and the maintainers will promptly review and remove or modify "
                "the referenced material if requested."
            )

            gpl_text = f"{gpl_intro}\n\n{self._load_gplv3_text()}"
            self._add_expandable_section("GNU General Public License", gpl_text, expanded=True)

            inc_text = self._load_incsan_text()
            self._add_expandable_section("OFL (Inclusive Sans)", inc_text, expanded=True)

            self._add_expandable_section("Notice For Team Salvato", team_salavo_text)

            self._add_expandable_section("Notice For maia arson crimew", maia_text)

            self.layout.addStretch(1)

            self._license_accepted = styled_checkbox("I have read these documents")
            self._license_accepted.setChecked(False)
            self.layout.addWidget(self._license_accepted)

            next_btn = styled_button("Next", primary=True)
            next_btn.setEnabled(False)
            self._license_accepted.toggled.connect(lambda checked: next_btn.setEnabled(bool(checked)))
            next_btn.clicked.connect(self._next_step)

            back_btn = styled_button("Back")
            back_btn.clicked.connect(self._prev_step)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(back_btn)
            row_layout.addStretch(1)
            row_layout.addWidget(next_btn)
            self.layout.addWidget(row)
            return

        if step == "time_format":
            self._title("Time Format")
            self._body_text("Choose your preferred time display.")

            use_24 = styled_switch("Use 24-hour time")
            use_24.setChecked(bool(self.window.config.use_24h_time))
            use_24.toggled.connect(lambda checked: self.window.set_setting("use_24h_time", bool(checked)))
            self.layout.addWidget(use_24)

            self.layout.addStretch(1)
            self._nav_row(back_enabled=True)
            return

        if step == "appearance":
            self._title("Light/Dark Mode")
            self._body_text("Choose how Deletescape looks.")

            dark = styled_switch("Enable dark mode")
            dark.setChecked(bool(self.window.config.dark_mode))
            dark.toggled.connect(lambda checked: self.window.set_setting("dark_mode", bool(checked)))
            self.layout.addWidget(dark)

            self.layout.addStretch(1)
            self._nav_row(back_enabled=True)
            return

        if step == "welcome":
            self._title("Welcome to Deletescape")
            self._body_text("Setup is ready to finish.")
            self.layout.addStretch(1)
            self._nav_row(back_enabled=False, next_text="Finish", next_handler=self._finish)
            return

    def _next_step(self) -> None:
        if self._step_index < (len(self._steps) - 1):
            self._step_index += 1
            self._render_step()

    def _prev_step(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def _finish(self) -> None:
        self.window.set_setting("setup_completed", True)
        self.window.launch_app("home")
