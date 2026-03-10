from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPixmap

from logger import PROCESS_START, get_logger
log = get_logger("wallpaper")

def load_pixmap(path: str | None) -> QPixmap | None:
    if not path:
        return None
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        pix = QPixmap(str(p))
        return None if pix.isNull() else pix
    except Exception:
        return None


def scale_crop_center(pixmap: QPixmap, target_size: QSize) -> QPixmap:
    """Scale to fill (KeepAspectRatioByExpanding) and crop center."""

    w = max(1, int(target_size.width()))
    h = max(1, int(target_size.height()))

    scaled = pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    sw = scaled.width()
    sh = scaled.height()

    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)

    return scaled.copy(QRect(x, y, w, h))
