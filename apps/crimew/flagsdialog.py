from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QScrollArea, QWidget, QLabel,
    QComboBox, QPushButton, QHBoxLayout, QMessageBox,
)
from PySide6.QtCore import Qt

import flags


class FlagsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flags")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(12)

        self._combos: dict[str, QComboBox] = {}

        data = flags.get_flags_cached()
        flags_list = data.get("flags") if isinstance(data, dict) else []

        for f in flags_list:
            fid = f.get("id")
            if not isinstance(fid, str) or not fid:
                continue

            name = f.get("name") or fid
            desc = f.get("description") or ""
            choices = f.get("choices") if isinstance(f.get("choices"), list) else []

            title_label = QLabel(f"<b>{name}</b>")
            title_label.setTextFormat(Qt.RichText)
            container_layout.addWidget(title_label)

            desc_label = QLabel(desc)
            desc_label.setWordWrap(True)
            container_layout.addWidget(desc_label)

            combo = QComboBox()
            for c in choices:
                cid = c.get("id")
                cname = c.get("name") or cid
                if cid is None:
                    continue
                combo.addItem(cname, cid)

            # determine current selection from config
            current = flags.get_experiment_choice(fid)
            # try to select matching data value, fallback to default choice
            index_to_select = 0
            for i in range(combo.count()):
                if combo.itemData(i) == current:
                    index_to_select = i
                    break
            combo.setCurrentIndex(index_to_select)

            container_layout.addWidget(combo)
            self._combos[fid] = combo

        container_layout.addStretch(1)
        self._scroll.setWidget(container)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btns.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _on_save(self):
        failed = []
        for fid, combo in self._combos.items():
            val = combo.currentData()
            try:
                ok = flags.set_experiment_choice(fid, val)
                if not ok:
                    failed.append(fid)
            except Exception:
                failed.append(fid)

        if failed:
            QMessageBox.warning(self, "Flags", f"Failed to save flags: {', '.join(failed)}")
        else:
            QMessageBox.information(self, "Flags", "Flags saved. Restart may be required for changes to take effect.")
        self.accept()
