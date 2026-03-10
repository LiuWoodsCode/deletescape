from PySide6.QtWidgets import QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QUrl


class _ColorSchemeHintInterceptor:
    """
    Injects a dark-mode client hint when OS dark mode is enabled.
    Avoids import-time dependency on QtWebEngineCore.
    """

    def __init__(self, window):
        self._window = window

    def as_qt_interceptor(self):
        from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

        window = self._window

        class Interceptor(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info):
                try:
                    if getattr(getattr(window, "config", None), "dark_mode", False):
                        info.setHttpHeader(
                            b"Sec-CH-Prefers-Color-Scheme",
                            b"dark",
                        )
                except Exception:
                    pass

        return Interceptor()


class App:
    def __init__(self, window, container):
        # Lazy imports (Qt6 module layout correct)
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton

        layout = QVBoxLayout()
        container.setLayout(layout)

        self.web = QWebEngineView()
        layout.addWidget(self.web, 1)

        # ---- Dark mode hint injection ----
        try:
            self._request_interceptor = (
                _ColorSchemeHintInterceptor(window).as_qt_interceptor()
            )
            self.web.page().profile().setUrlRequestInterceptor(
                self._request_interceptor
            )
        except Exception:
            self._request_interceptor = None

        # ---- Force dark mode (if available in this build) ----
        try:
            if hasattr(QWebEngineSettings, "ForceDarkMode"):
                self.web.settings().setAttribute(
                    QWebEngineSettings.ForceDarkMode,
                    bool(getattr(getattr(window, "config", None), "dark_mode", False)),
                )
        except Exception:
            pass

        # ---- Mobile user agent ----
        self.web.page().profile().setHttpUserAgent(
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Mobile Safari/537.36"
        )

        self.web.setUrl(QUrl("https://www.google.com/search?q=dedf1sh"))

        # ---- Bottom UI ----
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("Search or type address")

        self.back_btn = QPushButton("Back")
        self.fwd_btn = QPushButton("Fwd")
        self.reload_btn = QPushButton("Reload")

        addr_row = QHBoxLayout()
        addr_row.addWidget(self.addr, 1)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.back_btn)
        btn_row.addWidget(self.fwd_btn)
        btn_row.addWidget(self.reload_btn)
        btn_row.addStretch(1)

        bottom_bar = QVBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(4)
        bottom_bar.addLayout(addr_row)
        bottom_bar.addLayout(btn_row)

        layout.addLayout(bottom_bar)

        # ---- Page actions ----
        page = self.web.page()

        self._act_back = page.action(QWebEnginePage.Back)
        self._act_fwd = page.action(QWebEnginePage.Forward)
        self._act_reload = page.action(QWebEnginePage.Reload)
        self._act_stop = page.action(QWebEnginePage.Stop)

        self._is_loading = False

        def _sync_nav_buttons():
            try:
                self.back_btn.setEnabled(self._act_back.isEnabled())
                self.fwd_btn.setEnabled(self._act_fwd.isEnabled())
            except Exception:
                pass

        def _sync_reload_button():
            try:
                self.reload_btn.setText(
                    "Stop" if self._is_loading else "Reload"
                )
                self.reload_btn.setEnabled(True)
            except Exception:
                pass

        self.back_btn.setEnabled(False)
        self.fwd_btn.setEnabled(False)
        _sync_reload_button()

        # ---- Wiring ----
        self.back_btn.clicked.connect(
            lambda: page.triggerAction(QWebEnginePage.Back)
        )
        self.fwd_btn.clicked.connect(
            lambda: page.triggerAction(QWebEnginePage.Forward)
        )

        def _reload_or_stop():
            try:
                if self._is_loading:
                    page.triggerAction(QWebEnginePage.Stop)
                else:
                    page.triggerAction(QWebEnginePage.Reload)
            except Exception:
                pass

        self.reload_btn.clicked.connect(_reload_or_stop)
        self.addr.returnPressed.connect(self._navigate_from_bar)

        # ---- Sync events ----
        try:
            self.web.urlChanged.connect(self._sync_address_bar)
            self.web.titleChanged.connect(self._sync_title)

            self.web.loadStarted.connect(self._on_load_started)
            self.web.loadFinished.connect(self._on_load_finished)

            self._act_back.changed.connect(_sync_nav_buttons)
            self._act_fwd.changed.connect(_sync_nav_buttons)

            _sync_nav_buttons()
        except Exception:
            pass

    # ---- Loading handlers ----

    def _on_load_started(self):
        self._is_loading = True
        self.reload_btn.setText("Stop")

    def _on_load_finished(self, _ok):
        self._is_loading = False
        self.reload_btn.setText("Reload")

    # ---- Navigation API ----

    def open_url(self, url_or_query: str) -> None:
        text = (url_or_query or "").strip()
        if not text:
            return

        self.addr.setText(text)

        url = self._coerce_input_to_url(text)
        if url:
            self.web.setUrl(url)

    def _sync_address_bar(self, url):
        if not self.addr.hasFocus():
            self.addr.setText(url.toString())

    def _sync_title(self, title):
        try:
            w = self.web.window()
            if w:
                w.setWindowTitle(title)
        except Exception:
            pass

    def _navigate_from_bar(self):
        text = (self.addr.text() or "").strip()
        if not text:
            return

        url = self._coerce_input_to_url(text)
        if url:
            self.web.setUrl(url)

    def _coerce_input_to_url(self, text):
        try:
            if any(ch.isspace() for ch in text):
                encoded = bytes(QUrl.toPercentEncoding(text)).decode("ascii")
                return QUrl(f"https://www.google.com/search?q={encoded}")

            candidate = QUrl(text)
            if candidate.isValid() and candidate.scheme():
                return candidate

            if "." in text or "/" in text or ":" in text:
                return QUrl("https://" + text)

            encoded = bytes(QUrl.toPercentEncoding(text)).decode("ascii")
            return QUrl(f"https://www.google.com/search?q={encoded}")

        except Exception:
            return None