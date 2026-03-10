from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QLineEdit, QTextEdit, QMainWindow, QWidget

from virtual_keyboard import VirtualKeyboard

VIRTUAL_KEYBOARD_PERSISTENT_PROPERTY = "virtualKeyboardPersistent"
VIRTUAL_KEYBOARD_CLOSE_ON_ENTER_PROPERTY = "virtualKeyboardCloseOnEnter"

from logger import PROCESS_START, get_logger
log = get_logger("inputhelper")

class _KeyboardFocusFilter(QObject):
    def __init__(self, app, *, host_widget=None, manager=None):
        super().__init__(app)
        # If a manager is provided, use its virtual keyboard instance so
        # programmatic control and flags are shared.
        if manager is not None and hasattr(manager, "vk"):
            self._vk = manager.vk
        else:
            self._vk = VirtualKeyboard()
        self._host_widget = host_widget

    def _resolve_host(self, target: QWidget) -> QWidget:
        if self._host_widget is not None:
            return self._host_widget
        win = target.window()
        if isinstance(win, QMainWindow):
            cw = win.centralWidget()
            if cw is not None:
                return cw
        return win

    def eventFilter(self, obj, event):
        try:
            et = event.type()
        except Exception:
            return super().eventFilter(obj, event)

        if et == QEvent.FocusIn:
            target = obj
            # Only show our keyboard for common text widgets.
            if isinstance(target, (QLineEdit, QTextEdit)):
                persistent_prop = target.property(VIRTUAL_KEYBOARD_PERSISTENT_PROPERTY)
                persistent = bool(persistent_prop) if persistent_prop is not None else False
                close_on_enter_prop = target.property(VIRTUAL_KEYBOARD_CLOSE_ON_ENTER_PROPERTY)
                close_on_enter = True if close_on_enter_prop is None else bool(close_on_enter_prop)
                self._vk.show_for_widget(
                    target,
                    host=self._resolve_host(target),
                    persistent=persistent,
                    close_on_enter=close_on_enter,
                )
        elif et == QEvent.FocusOut:
            target = obj
            if isinstance(target, (QLineEdit, QTextEdit)):
                # Respect the keyboard's configured behavior: if the
                # keyboard was requested to remain open (persistent), do
                # not hide on focus loss.
                try:
                    if getattr(self._vk, "_close_on_focus_loss", True):
                        try:
                            # Prefer using the keyboard's close helper.
                            self._vk.close_keyboard()
                        except Exception:
                            self._vk.hide()
                except Exception:
                    try:
                        self._vk.hide()
                    except Exception:
                        pass

        return super().eventFilter(obj, event)


def install_focus_filter(app, *, host_widget=None):
    """Install a global event filter that shows our custom virtual keyboard
    when widgets gain keyboard focus. `host_widget` is an optional widget
    used for positioning/parenting the keyboard (e.g. Deletescape.root).
    """
    f = _KeyboardFocusFilter(app, host_widget=host_widget)
    app.installEventFilter(f)
    return f
