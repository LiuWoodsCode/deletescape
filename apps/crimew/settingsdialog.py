from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QCheckBox, QPushButton, QComboBox, QSpinBox, QLineEdit, QGroupBox,
    QScrollArea, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt

import flags


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Create tab widget
        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        # Add settings pages if flags are enabled
        config = flags.get_config_cached()
        exps = config.get("experiments", {}).get("flags", {})

        if exps.get("user_data_management") == "enabled":
            self._tabs.addTab(self._create_user_data_page(), "User data")

        if exps.get("site_permission_settings") == "enabled":
            self._tabs.addTab(self._create_site_permissions_page(), "Site permissions")

        if exps.get("deadname_replacement_engine") == "enabled":
            self._tabs.addTab(self._create_text_replacement_page(), "Deadname replacement")

        if flags.resolve_bool_flag("new_omnibox", default_value=False):
            self._tabs.addTab(self._create_search_page(), "Search")

        # If no flags are enabled, show a message
        if self._tabs.count() == 0:
            self._tabs.addTab(self._create_empty_page(), "No features enabled")

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _create_scroll_widget(self):
        """Create a scrollable container for settings."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        scroll.setWidget(container)
        return scroll, container, layout

    def _create_empty_page(self) -> QWidget:
        """Create an empty page when no features are enabled."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("No experimental features enabled\n\n"
                      "To use these settings, enable them in Debug > Flags")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()
        return widget

    def _create_user_data_page(self) -> QWidget:
        """Create user data management settings page."""
        scroll, container, layout = self._create_scroll_widget()

        title = QLabel("<b>User data</b>")
        title.setTextFormat(Qt.RichText)
        container.layout().addWidget(title)

        desc = QLabel("Manage your browsing data")
        desc.setWordWrap(True)
        container.layout().addWidget(desc)

        # Dummy settings
        group = QGroupBox("Clear data automatically")
        form = QFormLayout()

        file_check = QCheckBox("When closing browser")
        form.addRow("Cookies and site data:", file_check)

        cache_check = QCheckBox("When closing browser")
        form.addRow("Cached images and files:", cache_check)

        history_check = QCheckBox("When closing browser")
        form.addRow("Browsing history:", history_check)

        group.setLayout(form)
        container.layout().addWidget(group)

        # Storage quota section
        storage_group = QGroupBox("Storage")
        storage_form = QFormLayout()
        storage_label = QLabel("Used: 2.4 MB / 50 MB")
        storage_form.addRow("Cache storage:", storage_label)
        storage_group.setLayout(storage_form)
        container.layout().addWidget(storage_group)

        container.layout().addStretch()
        return scroll

    def _create_search_page(self) -> QWidget:
        """Create search provider settings page."""
        scroll, container, layout = self._create_scroll_widget()

        title = QLabel("<b>Search</b>")
        title.setTextFormat(Qt.RichText)
        container.layout().addWidget(title)

        desc = QLabel("Choose which search provider the omnibox uses for search queries and suggestions")
        desc.setWordWrap(True)
        container.layout().addWidget(desc)

        provider_group = QGroupBox("Search provider")
        form = QFormLayout()

        self._search_provider_combo = QComboBox()
        self._search_provider_combo.addItem("Google", "google")
        self._search_provider_combo.addItem("Bing", "bing")
        self._search_provider_combo.addItem("DuckDuckGo", "duckduckgo")

        current_provider = flags.get_search_provider()
        selected_index = 0
        for i in range(self._search_provider_combo.count()):
            if self._search_provider_combo.itemData(i) == current_provider:
                selected_index = i
                break
        self._search_provider_combo.setCurrentIndex(selected_index)
        self._search_provider_combo.currentIndexChanged.connect(self._save_search_settings)

        form.addRow("Provider:", self._search_provider_combo)
        provider_group.setLayout(form)
        container.layout().addWidget(provider_group)

        container.layout().addStretch()
        return scroll

    def _save_search_settings(self):
        combo = getattr(self, "_search_provider_combo", None)
        if combo is None:
            return

        provider = combo.currentData()
        if not flags.set_search_provider(provider):
            QMessageBox.warning(self, "Search", "Failed to save search provider setting.")

    def _create_site_permissions_page(self) -> QWidget:
        """Create site permissions settings page."""
        scroll, container, layout = self._create_scroll_widget()

        title = QLabel("<b>Site permissions</b>")
        title.setTextFormat(Qt.RichText)
        container.layout().addWidget(title)

        desc = QLabel("Choose which permissions websites can request from you")
        desc.setWordWrap(True)
        container.layout().addWidget(desc)

        # Permissions list
        permissions = [
            ("Camera", "Ask before allowing"),
            ("Microphone", "Ask before allowing"),
            ("Location", "Ask before allowing"),
            ("Notifications", "Ask before allowing"),
            ("Clipboard", "Ask before allowing"),
            ("MIDI devices", "Ask before allowing"),
        ]

        for perm_name, default_val in permissions:
            group = QGroupBox(perm_name)
            form = QFormLayout()
            combo = QComboBox()
            combo.addItems(["Ask before allowing", "Always allow", "Always deny"])
            combo.setCurrentText(default_val)
            form.addRow(perm_name + ":", combo)
            group.setLayout(form)
            container.layout().addWidget(group)

        container.layout().addStretch()
        return scroll

    def _create_text_replacement_page(self) -> QWidget:
        """Create deadname replacement settings page."""
        scroll, container, layout = self._create_scroll_widget()

        title = QLabel("<b>Deadname replacement</b>")
        title.setTextFormat(Qt.RichText)
        container.layout().addWidget(title)

        desc = QLabel("Replace deadnames with chosen names of trans and nonbinary people on websites. "
                     "<br><br><b>Examples:</b><br>"
                     "• Till Kottmann → maia arson crimew<br>"
                     "• Leif Chappelle → Lena Raine")
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.RichText)
        container.layout().addWidget(desc)

        # Name list source
        source_group = QGroupBox("Name list source")
        source_form = QFormLayout()

        source_mode = QComboBox()
        source_mode.addItems([
            "Use built-in list",
            "Query update servers",
            "Both (fallback to built-in)"
        ])
        source_mode.setCurrentIndex(1)
        source_form.addRow("Source:", source_mode)

        status_label = QLabel("Built-in: 127 entries\nServers: 234 entries (updated today)")
        status_label.setWordWrap(True)
        source_form.addRow("Status:", status_label)

        source_group.setLayout(source_form)
        container.layout().addWidget(source_group)

        # Update frequency
        update_group = QGroupBox("Update settings")
        update_form = QFormLayout()

        update_freq = QComboBox()
        update_freq.addItems([
            "Never",
            "On startup",
            "Daily",
            "Weekly",
            "Monthly"
        ])
        update_freq.setCurrentIndex(2)
        update_form.addRow("Check for updates:", update_freq)

        auto_update = QCheckBox("Automatically update when new entries are available")
        auto_update.setChecked(True)
        update_form.addRow("", auto_update)

        update_group.setLayout(update_form)
        container.layout().addWidget(update_group)

        # Enable/disable
        enable_group = QGroupBox("Feature")
        enable_form = QFormLayout()

        enable_check = QCheckBox("Use deadname replacement on websites")
        enable_check.setChecked(True)
        enable_form.addRow("", enable_check)

        privacy_label = QLabel(
            "<small>Your browsing isn't sent anywhere. Replacement happens entirely in your browser.</small>"
        )
        privacy_label.setWordWrap(True)
        privacy_label.setTextFormat(Qt.RichText)
        enable_form.addRow("", privacy_label)

        enable_group.setLayout(enable_form)
        container.layout().addWidget(enable_group)

        container.layout().addStretch()
        return scroll