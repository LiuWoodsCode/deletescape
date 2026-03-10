from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fs_layout import get_user_data_layout


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


def get_default_dcim_dir() -> Path:
    return get_user_data_layout(Path(__file__).resolve().parent).user_dcim


def list_gallery_photos(dcim_dir: Path) -> list[Path]:
    if not dcim_dir.exists() or not dcim_dir.is_dir():
        return []

    photos: list[Path] = []
    try:
        for path in dcim_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in IMAGE_EXTS:
                photos.append(path)
    except Exception:
        return []

    def sort_key(p: Path):
        try:
            return p.stat().st_mtime
        except Exception:
            return 0

    photos.sort(key=sort_key, reverse=True)
    return photos


def _make_thumbnail_icon(path: Path, size_px: int) -> QIcon:
    pix = QPixmap(str(path))
    if pix.isNull():
        return QIcon()
    pix = pix.scaled(size_px, size_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(pix)


@dataclass
class PhotoPickResult:
    selected_path: str | None


class PhotoPickerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        dcim_dir: Path,
        title: str = "Select Photo",
        instruction: str = "Pick a photo",
        thumb_size_px: int = 96,
        columns: int = 3,
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)

        self._dcim_dir = dcim_dir
        self._thumb_size_px = int(thumb_size_px)
        self._columns = max(1, int(columns))

        self.selected_path: str | None = None

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        self.setLayout(root)

        header = QLabel(instruction)
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        photos = list_gallery_photos(self._dcim_dir)

        if not photos:
            empty = QLabel(f"No photos found in {self._dcim_dir.name}.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            root.addWidget(empty, 1)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            root.addWidget(scroll, 1)

            host = QWidget()
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            host.setLayout(grid)
            scroll.setWidget(host)

            row = col = 0
            for photo in photos:
                btn = QToolButton()
                btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                btn.setText(photo.name)
                btn.setIcon(_make_thumbnail_icon(photo, self._thumb_size_px))
                btn.setIconSize(QPixmap(self._thumb_size_px, self._thumb_size_px).size())
                btn.setFixedSize(self._thumb_size_px + 34, self._thumb_size_px + 48)
                btn.clicked.connect(lambda _=False, p=str(photo): self._select_and_close(p))

                grid.addWidget(btn, row, col)
                col += 1
                if col >= self._columns:
                    col = 0
                    row += 1

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

        self.resize(420, 640)

    def _select_and_close(self, path: str) -> None:
        self.selected_path = path
        self.accept()


def request_photo_from_gallery(
    parent: QWidget | None,
    *,
    dcim_dir: Path | None = None,
    title: str = "Select Photo",
    instruction: str = "Pick a photo",
) -> str | None:
    dcim_dir = dcim_dir or get_default_dcim_dir()
    try:
        dcim_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    dlg = PhotoPickerDialog(parent, dcim_dir=dcim_dir, title=title, instruction=instruction)
    result = dlg.exec_()
    if result == QDialog.Accepted:
        return dlg.selected_path
    return None
