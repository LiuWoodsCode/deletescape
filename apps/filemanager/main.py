from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMenu,
    QFileDialog,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QInputDialog,
)
import shutil

from file_handlers import get_handlers_for_path, open_with_app

from logger import get_logger

log = get_logger("filemanager")


def _user_root() -> Path:
    # App-owned canonical user files path.
    return Path(__file__).resolve().parents[2] / "userdata" / "User"


def _is_text_file(path: Path) -> bool:
    try:
        return path.suffix.lower() in {".txt", ".py", ".md", ".json", ".cfg", ".ini", ".log"}
    except Exception:
        return False


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._root = _user_root()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self._current: Path = self._root

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        container.setLayout(layout)

        top = QHBoxLayout()
        self._path_label = QLabel(self._display_path(self._current))
        top.addWidget(self._path_label, 1)

        up = QPushButton("Up")
        up.clicked.connect(self._go_up)
        top.addWidget(up)

        newf = QPushButton("New folder")
        newf.clicked.connect(self._new_folder)
        top.addWidget(newf)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        top.addWidget(refresh)

        layout.addLayout(top)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self._list, 1)

        bottom = QHBoxLayout()
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self._open_selected)
        bottom.addWidget(open_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(delete_btn)

        layout.addLayout(bottom)

        self._refresh()

    def _set_current(self, p: Path) -> None:
        try:
            self._current = p
            self._path_label.setText(self._display_path(self._current))
            self._refresh()
        except Exception:
            log.exception("Failed to set current dir")

    def _go_up(self) -> None:
        if self._current == self._root:
            return
        self._set_current(self._current.parent)

    def _new_folder(self) -> None:
        name, ok = QInputDialog.getText(self.container, "New folder", "Folder name:")
        if not ok or not name:
            return
        try:
            (self._current / name).mkdir(parents=False, exist_ok=False)
            self._refresh()
        except Exception:
            QMessageBox.warning(self.container, "Error", "Failed to create folder")

    def _refresh(self) -> None:
        self._list.clear()
        try:
            entries = sorted(self._current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            entries = []

        for p in entries:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, str(p))

            widget = self._make_item_widget(p)

            # Set icon
            item.setIcon(self._icon_for_path(p))

            # Ensure proper item height
            hint = widget.sizeHint()
            hint.setHeight(45)     # Increase height here
            item.setSizeHint(hint)

            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _display_path(self, p: Path) -> str:
        try:
            rel = p.relative_to(self._root)
            s = str(rel)
            if s == ".":
                return "/"
            # normalize to forward slashes for display
            return "/" + s.replace("\\", "/")
        except Exception:
            s = str(p).replace("\\", "/")
            return s

    def _icon_for_path(self, path: Path) -> QIcon:
        try:
            if path.is_dir():
                return QIcon.fromTheme("folder")
            ext = path.suffix.lower()
            mapping = {
                ".png": "image-x-generic",
                ".jpg": "image-x-generic",
                ".jpeg": "image-x-generic",
                ".gif": "image-x-generic",
                ".bmp": "image-x-generic",
                ".svg": "image-x-generic",
                ".mp3": "audio-x-generic",
                ".wav": "audio-x-generic",
                ".ogg": "audio-x-generic",
                ".flac": "audio-x-generic",
                ".mp4": "video-x-generic",
                ".mkv": "video-x-generic",
                ".webm": "video-x-generic",
                ".pdf": "application-pdf",
                ".zip": "package-x-generic",
                ".tar": "package-x-generic",
                ".gz": "package-x-generic",
                ".7z": "package-x-generic",
                ".py": "text-x-script",
                ".txt": "text-x-generic",
                ".md": "text-x-generic",
                ".json": "application-json",
                ".html": "text-html",
                ".htm": "text-html",
                ".css": "text-x-generic",
                ".exe": "application-x-executable",
            }
            icon_name = mapping.get(ext)
            if icon_name:
                icon = QIcon.fromTheme(icon_name)
                if not icon.isNull():
                    return icon
            if _is_text_file(path):
                return QIcon.fromTheme("text-x-generic")
            # fallback generic binary icon
            return QIcon.fromTheme("application-octet-stream")
        except Exception:
            return QIcon.fromTheme("text-x-generic")

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        p = Path(item.data(Qt.UserRole))
        if p.is_dir():
            self._set_current(p)
            return
        # Open file with default handler (fallback: show properties)
        handlers = get_handlers_for_path(p)
        if handlers:
            # pick first registered handler
            open_with_app(self.window, handlers[0]["app_id"], p)
            return
        # No handler found -> show error message
        ext = p.suffix if p.suffix else "(no extension)"
        QMessageBox.warning(self.container, "Open", f"No app installed for {ext} file")

    def _open_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        p = Path(item.data(Qt.UserRole))
        if p.is_dir():
            self._set_current(p)
            return
        handlers = get_handlers_for_path(p)
        if handlers:
            open_with_app(self.window, handlers[0]["app_id"], p)
            return
        ext = p.suffix if p.suffix else "(no extension)"
        QMessageBox.warning(self.container, "Open", f"No app installed for {ext} file")

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        p = Path(item.data(Qt.UserRole))
        resp = QMessageBox.question(self.container, "Delete", f"Delete {p.name}?", QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        try:
            if p.is_dir():
                for child in p.rglob("*"):
                    try:
                        if child.is_dir():
                            child.rmdir()
                        else:
                            child.unlink()
                    except Exception:
                        pass
                p.rmdir()
            else:
                p.unlink()
            self._refresh()
        except Exception:
            QMessageBox.warning(self.container, "Error", "Failed to delete")

    def _show_preview(self, p: Path) -> None:
        # Deprecated: per design we no longer preview files here.
        return

    def _make_item_widget(self, path: Path) -> QWidget:
        w = QWidget()
        v = QVBoxLayout()
        v.setContentsMargins(6, 4, 6, 4)
        
        name = QLabel(path.name)
        info = ""
        try:
            if path.exists():
                st = path.stat()
                if path.is_dir():
                    info = f"Folder — {len(list(path.iterdir()))} items"
                else:
                    size = st.st_size
                    mtime = st.st_mtime
                    info = f"{size} bytes — modified {int(mtime)}"
        except Exception:
            info = ""

        info_label = QLabel(info)
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        v.addWidget(name)
        v.addWidget(info_label)
        w.setLayout(v)
        return w

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        p = Path(item.data(Qt.UserRole))
        menu = QMenu()

        # Open In submenu
        handlers = get_handlers_for_path(p)
        if handlers:
            open_in_menu = menu.addMenu("Open in")
            for h in handlers:
                act = QAction(h.get("display_name") or h.get("app_id"), open_in_menu)
                def _make_open(hid):
                    return lambda: open_with_app(self.window, hid, p)
                act.triggered.connect(_make_open(h.get("app_id")))
                open_in_menu.addAction(act)

        open_default = QAction("Open", menu)
        open_default.triggered.connect(lambda: self._open_selected())
        menu.addAction(open_default)

        copy_act = QAction("Copy", menu)
        def _copy():
            dst = QFileDialog.getExistingDirectory(self.container, "Copy to")
            if not dst:
                return
            try:
                if p.is_dir():
                    shutil.copytree(str(p), str(Path(dst) / p.name))
                else:
                    shutil.copy2(str(p), str(Path(dst) / p.name))
            except Exception:
                QMessageBox.warning(self.container, "Error", "Copy failed")
        copy_act.triggered.connect(_copy)
        menu.addAction(copy_act)

        rename_act = QAction("Rename", menu)
        def _rename():
            new, ok = QInputDialog.getText(self.container, "Rename", "New name:", text=p.name)
            if not ok or not new:
                return
            try:
                p.rename(p.with_name(new))
                self._refresh()
            except Exception:
                QMessageBox.warning(self.container, "Error", "Rename failed")
        rename_act.triggered.connect(_rename)
        menu.addAction(rename_act)

        delete_act = QAction("Delete", menu)
        delete_act.triggered.connect(self._delete_selected)
        menu.addAction(delete_act)

        prop_act = QAction("Properties", menu)
        prop_act.triggered.connect(lambda: self._show_properties(p))
        menu.addAction(prop_act)

        menu.exec_(self._list.mapToGlobal(pos))

    def _show_properties(self, p: Path) -> None:
        try:
            if not p.exists():
                QMessageBox.information(self.container, "Properties", "(missing)")
                return
            st = p.stat()
            details = []
            details.append(f"Path: {str(p)}")
            details.append(f"Type: {'Folder' if p.is_dir() else 'File'}")
            details.append(f"Size: {st.st_size} bytes")
            details.append(f"Modified: {int(st.st_mtime)}")
            QMessageBox.information(self.container, "Properties", "\n".join(details))
        except Exception:
            QMessageBox.information(self.container, "Properties", "(error)")
