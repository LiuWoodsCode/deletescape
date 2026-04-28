from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QObject, Qt, QUrl, QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtCore import QLoggingCategory

from browser import Browser  # Uses the existing browser module (no UI embedded here)

try:
    from logger import get_logger
    log = get_logger("crimew")
except:
    if __name__ == "__main__":
        import logging
        logging.basicConfig(level=logging.DEBUG)
        log = logging.getLogger("crimew")
class App(QObject):
    """
    Wrapper App for the Simple Browser example that:
    - Follows the same (window, container) constructor signature as your other apps.
    - Does NOT embed or recreate UI directly; it uses the `browser` module.
    - Configures QWebEngine global settings similarly to the example.
    - Manages a Browser window created via `Browser.create_hidden_window()`.

    Usage:
        app = App(host_window, host_container, start_url="https://www.qt.io")
        app.show()  # shows the browser window managed by the Browser module
    """

    def __init__(
        self,
        window,
        container,
        *,
        start_url: Optional[str] = None,
        enable_debug_logging: bool = False,
        window_icon: Optional[QIcon] = None,
    ):
        super().__init__(container)
        self.window = window
        self.container = container

        if enable_debug_logging:
            # Mirrors the example's debug switch
            QLoggingCategory.setFilterRules("qt.webenginecontext.debug=true")

        # --- Global WebEngine Settings similar to the example ---
        try:
            s = QWebEngineProfile.defaultProfile().settings()
            s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            s.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, True)
            s.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, True)
        except Exception as e:
            log.warning(f"Unable to configure WebEngine settings: {e}")

        # --- Create Browser (no direct UI embedding) ---
        self._browser = Browser()
        # Request an embedded browser UI inside the provided container
        self._browser_window = self._browser.create_hidden_window(parent_container=self.container)
        log.debug("Create hidden window")

        # Navigate to initial URL (default "chrome://qt" like the sample)
        initial = QUrl.fromUserInput(start_url) if start_url else QUrl("chrome://qt")
        self.show()
        try:
            self._browser_window.tab_widget().set_url(initial)
            log.debug("Set inital url")
        except Exception as e:
            log.error(f"Failed to set initial URL: {e}")

        # We DO NOT parent or embed the Browser window into `container` on purpose.
        # The Browser module controls its own toplevel window. This class just manages it.

    # -------------------------
    # Public control methods
    # -------------------------
    def show(self):
        """Show the Browser's managed main window."""
        try:
            self._browser_window.show()
            self._browser_window.raise_()
            self._browser_window.activateWindow()
        except Exception as e:
            log.error(f"Failed to show browser window: {e}")

    def hide(self):
        """Hide the Browser's managed main window."""
        try:
            self._browser_window.hide()
        except Exception:
            pass

    def close(self):
        """Close the Browser window (and release resources)."""
        try:
            self._browser_window.close()
        except Exception:
            pass

    def navigate(self, url: str | QUrl):
        """Navigate current tab to the given URL."""
        try:
            qurl = QUrl.fromUserInput(url) if isinstance(url, str) else url
            self._browser_window.tab_widget().set_url(qurl)
        except Exception as e:
            log.error(f"Navigate failed: {e}")

    def new_tab(self, url: str | QUrl):
        """Open a new tab with the given URL."""
        try:
            qurl = QUrl.fromUserInput(url) if isinstance(url, str) else url
            self._browser_window.tab_widget().new_tab(qurl)
        except Exception as e:
            log.error(f"New tab failed: {e}")

    def back(self):
        """Navigate back in current tab."""
        try:
            self._browser_window.tab_widget().current_webview().back()
        except Exception:
            pass

    def forward(self):
        """Navigate forward in current tab."""
        try:
            self._browser_window.tab_widget().current_webview().forward()
        except Exception:
            pass

    def reload(self):
        """Reload the current tab."""
        try:
            self._browser_window.tab_widget().current_webview().reload()
        except Exception:
            pass

    # Optional: if host needs access to the actual window
    def browser_window(self):
        return self._browser_window

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

if __name__ == "__main__":
    # Open the browser window directly if this file is run standalone (for testing)
    # Use a GUI application (QApplication) rather than QCoreApplication to
    # avoid segfaults when creating GUI/WebEngine windows.
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    test_app = App(None, None, start_url="https://www.qt.io", enable_debug_logging=True)
    test_app.show()
    sys.exit(app.exec())
    