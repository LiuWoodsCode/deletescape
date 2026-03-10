from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QWidget

from logger import get_logger


log = get_logger("buttons")


class ButtonAction(str, Enum):
    HOME = "home"
    POWER = "power"


@dataclass(frozen=True)
class ButtonBinding:
    action: ButtonAction
    sequence: QKeySequence


class ButtonManager:
    """Minimal abstraction layer for hardware/keyboard "buttons".

    For now, it only supports Qt keyboard shortcuts, but callers interact with
    high-level actions (e.g., HOME) instead of raw key sequences, so it should be easy to implement any button (GPIO, I2C,)

    This allows use of physical buttons on a device through Linux kernel events or similar.
    """

    def __init__(self, host: QWidget):
        self._host = host
        self._shortcuts: list[QShortcut] = []

    def bind_global(self, binding: ButtonBinding, handler: Callable[[], None]) -> None:
        shortcut = QShortcut(binding.sequence, self._host)
        shortcut.setContext(Qt.ApplicationShortcut)

        def _wrapped() -> None:
            log.debug(
                "Button activated",
                extra={"action": str(binding.action), "sequence": binding.sequence.toString()},
            )
            try:
                handler()
            except Exception:
                log.exception(
                    "Button handler crashed",
                    extra={"action": str(binding.action), "sequence": binding.sequence.toString()},
                )
                raise

        log.debug(
            "Bind global button",
            extra={"action": str(binding.action), "sequence": binding.sequence.toString()},
        )

        shortcut.activated.connect(_wrapped)
        self._shortcuts.append(shortcut)

    @staticmethod
    def chord(sequence: str) -> QKeySequence:
        return QKeySequence(sequence)
