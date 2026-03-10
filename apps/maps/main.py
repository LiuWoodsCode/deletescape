from PySide6.QtWidgets import QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QUrl

class App:
    def __init__(self, window, container):
        # Lazy imports (Qt6 module layout correct)
        from PySide6.QtWebEngineWidgets import QWebEngineView

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)   # <- remove outer margins
        layout.setSpacing(0)                    # <- remove spacing between widgets
        container.setLayout(layout)

        self.web = QWebEngineView()
        self.web.setContentsMargins(0, 0, 0, 0) # <- ensure the widget has no padding
        layout.addWidget(self.web, 1)

        # ---- Mobile user agent ----
        self.web.page().profile().setHttpUserAgent(
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Mobile Safari/537.36"
        )

        self.web.setUrl(QUrl("https://maps.google.com"))