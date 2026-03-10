from __future__ import annotations

import ast
import io
import subprocess
import traceback
from contextlib import redirect_stderr, redirect_stdout

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QVBoxLayout


class _InputHistoryFilter(QObject):
    def __init__(self, app: "App"):
        super().__init__(app.container)
        self._app = app

    def eventFilter(self, obj, event):
        try:
            if obj is self._app._input and event.type() == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Up:
                    self._app._history_up()
                    return True
                if key == Qt.Key_Down:
                    self._app._history_down()
                    return True
                if key == Qt.Key_Escape:
                    self._app._input.setText("")
                    self._app._history_idx = None
                    return True
        except Exception:
            # Never allow the event filter to break typing.
            return False
        return False


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._mode: str = "python"  # python | shell

        self._globals: dict = {
            "__name__": "__terminal__",
            "__package__": None,
        }
        self._locals: dict = {}

        self._history: list[str] = []
        self._history_idx: int | None = None
        self._history_saved_current: str = ""

        root = QVBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        container.setLayout(root)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        try:
            self._output.document().setMaximumBlockCount(2000)
        except Exception:
            pass
        root.addWidget(self._output, 1)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Enter Python (or 'help')")
        self._input_filter = _InputHistoryFilter(self)
        self._input.installEventFilter(self._input_filter)
        root.addWidget(self._input)

        row = QHBoxLayout()
        row.setSpacing(8)

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._run_current)
        row.addWidget(run_btn)

        self._mode_btn = QPushButton("Mode: Python")
        self._mode_btn.clicked.connect(self._toggle_mode)
        row.addWidget(self._mode_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        row.addWidget(clear_btn)

        help_btn = QPushButton("Help")
        help_btn.clicked.connect(self._show_help)
        row.addWidget(help_btn)

        row.addStretch(1)
        root.addLayout(row)

        mono = QFont("Consolas")
        if not mono.exactMatch():
            mono = QFont("Courier New")
        mono.setPointSize(10)
        self._output.setFont(mono)
        self._input.setFont(mono)

        self._banner()

        try:
            self._input.returnPressed.connect(self._run_current)
        except Exception:
            pass

    # -------------------- UI helpers --------------------
    def _append(self, text: str) -> None:
        if text is None:
            return
        s = str(text)
        if not s:
            self._output.appendPlainText("")
            return
        # Ensure we don't accidentally add embedded carriage returns.
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        for line in s.split("\n"):
            self._output.appendPlainText(line)
        try:
            self._output.verticalScrollBar().setValue(self._output.verticalScrollBar().maximum())
        except Exception:
            pass

    def _banner(self) -> None:
        self._append("MobileTerminal for Deletescape Shell")
        self._append("Mode: Python (toggle with Mode button)")
        self._append("Commands: help, clear, reset")
        self._append("")

    def _prompt(self) -> str:
        return ">>> " if self._mode == "python" else "$ "

    def _sync_mode_ui(self) -> None:
        if self._mode == "python":
            self._mode_btn.setText("Mode: Python")
            self._input.setPlaceholderText("Enter Python (or 'help')")
        else:
            self._mode_btn.setText("Mode: Shell")
            self._input.setPlaceholderText("Enter shell command (or 'help')")

    def _toggle_mode(self) -> None:
        self._mode = "shell" if self._mode == "python" else "python"
        self._sync_mode_ui()
        self._append(f"(mode: {self._mode})")

    # -------------------- History --------------------
    def _push_history(self, cmd: str) -> None:
        cmd = (cmd or "").rstrip("\n")
        if not cmd.strip():
            return
        if self._history and self._history[-1] == cmd:
            return
        self._history.append(cmd)
        if len(self._history) > 200:
            self._history = self._history[-200:]

    def _history_up(self) -> None:
        if not self._history:
            return
        if self._history_idx is None:
            self._history_saved_current = self._input.text()
            self._history_idx = len(self._history) - 1
        else:
            self._history_idx = max(0, self._history_idx - 1)
        self._input.setText(self._history[self._history_idx])

    def _history_down(self) -> None:
        if self._history_idx is None:
            return
        self._history_idx += 1
        if self._history_idx >= len(self._history):
            self._history_idx = None
            self._input.setText(self._history_saved_current)
            return
        self._input.setText(self._history[self._history_idx])

    # -------------------- Commands --------------------
    def _clear(self) -> None:
        self._output.clear()
        self._append(self._prompt())

    def _reset(self) -> None:
        self._globals = {
            "__name__": "__terminal__",
            "__package__": None,
        }
        self._locals = {}
        self._append("(session reset)")

    def _show_help(self) -> None:
        self._append(
            "\n".join(
                [
                    "Commands:",
                    "  help  - show this message",
                    "  clear - clear the screen",
                    "  reset - reset Python session",
                    "",
                    "Notes:",
                    "  - Mode: Python evaluates code; expressions show repr.",
                    "  - Mode: Shell runs system commands (stdout/stderr captured).",
                ]
            )
        )
        self._append("")

    def _go_home(self) -> None:
        go_home = getattr(self.window, "go_home", None)
        if callable(go_home):
            go_home()

    def _run_current(self) -> None:
        cmd = (self._input.text() or "").rstrip("\n")
        self._input.setText("")
        self._history_idx = None

        if not cmd.strip():
            self._append(self._prompt())
            return

        self._push_history(cmd)
        self._append(f"{self._prompt()}{cmd}")

        lowered = cmd.strip().lower()
        if lowered in {"help", "?"}:
            self._show_help()
            return
        if lowered in {"clear", "cls"}:
            self._clear()
            return
        if lowered in {"reset"}:
            self._reset()
            return

        if self._mode == "shell":
            self._run_shell(cmd)
            self._append("")
            return

        out = io.StringIO()
        err = io.StringIO()

        try:
            code_obj, is_expr = self._compile(cmd)
            with redirect_stdout(out), redirect_stderr(err):
                if is_expr:
                    value = eval(code_obj, self._globals, self._locals)
                    if value is not None:
                        print(repr(value))
                else:
                    exec(code_obj, self._globals, self._locals)
        except Exception:
            tb = traceback.format_exc()
            self._append(tb.rstrip("\n"))
        finally:
            o = out.getvalue()
            e = err.getvalue()
            if o:
                self._append(o.rstrip("\n"))
            if e:
                self._append(e.rstrip("\n"))

        self._append("")

    def _run_shell(self, cmd: str) -> None:
        try:
            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=None,
            )
            if completed.stdout:
                self._append(completed.stdout.rstrip("\n"))
            if completed.stderr:
                self._append(completed.stderr.rstrip("\n"))
            self._append(f"(exit: {int(completed.returncode)})")
        except Exception:
            self._append(traceback.format_exc().rstrip("\n"))

    def _compile(self, src: str):
        """Return (code_obj, is_expr)."""
        src = src.strip("\n")

        # Try expression first.
        try:
            expr = ast.parse(src, mode="eval")
            code_obj = compile(expr, "<terminal>", "eval")
            return code_obj, True
        except SyntaxError:
            pass

        # Then statements.
        mod = ast.parse(src, mode="exec")
        code_obj = compile(mod, "<terminal>", "exec")
        return code_obj, False
