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

        self._license_accepted: QCheckBox | None = None

        self._render_license()

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
        header = HeaderBar(
            title,
            show_back=False,
        )
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

    def _render_license(self) -> None:
        self._clear_layout()

        self._title("License Agreement")

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