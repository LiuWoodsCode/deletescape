import sys
import subprocess
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMenu,
)


class Taskbar(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PyTaskbar")

        # Make it look like a taskbar
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )

        self.setFixedHeight(40)

        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(
            screen.x(),
            screen.bottom() - self.height(),
            screen.width(),
            self.height(),
        )

        self.setStyleSheet("""
            QWidget {
                background-color: #202020;
                color: white;
                font-size: 12px;
            }

            QPushButton {
                background-color: #303030;
                border: 1px solid #505050;
                padding: 5px 10px;
            }

            QPushButton:hover {
                background-color: #404040;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Start button
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.show_start_menu)
        layout.addWidget(self.start_button)

        # Example app launchers
        self.notepad_button = QPushButton("Notepad")
        self.notepad_button.clicked.connect(
            lambda: self.launch("notepad")
        )
        layout.addWidget(self.notepad_button)

        self.calc_button = QPushButton("Calculator")
        self.calc_button.clicked.connect(
            lambda: self.launch("calc")
        )
        layout.addWidget(self.calc_button)

        layout.addStretch()

        # Clock
        self.clock = QLabel()
        layout.addWidget(self.clock)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)

        self.update_clock()

    def update_clock(self):
        self.clock.setText(
            datetime.now().strftime("%I:%M:%S %p")
        )

    def launch(self, command):
        try:
            subprocess.Popen(command)
        except Exception as e:
            print(f"Failed to launch {command}: {e}")

    def show_start_menu(self):
        menu = QMenu(self)

        notepad_action = QAction("Notepad", self)
        notepad_action.triggered.connect(
            lambda: self.launch("notepad")
        )

        calc_action = QAction("Calculator", self)
        calc_action.triggered.connect(
            lambda: self.launch("calc")
        )

        exit_action = QAction("Exit Taskbar", self)
        exit_action.triggered.connect(QApplication.quit)

        menu.addAction(notepad_action)
        menu.addAction(calc_action)
        menu.addSeparator()
        menu.addAction(exit_action)

        menu.exec(
            self.start_button.mapToGlobal(
                self.start_button.rect().bottomLeft()
            )
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)

    taskbar = Taskbar()
    taskbar.show()

    sys.exit(app.exec())