import os
import sys
import json
import html
import re
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List

import logging

from deletescapeui import get_theme, qcolor_css, styled_button, styled_line_edit

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("assistant.frontend.main")

from PySide6.QtCore import QObject, Qt, QThread, Signal, QByteArray, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QUrl
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QMessageBox,
    QWidget,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextBrowser,
    QSizePolicy,
    QGraphicsOpacityEffect,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from card_renderer import render_card_html

DEFAULT_TIMEOUT = 8.0

CARD_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<style>{style}</style>
</head>
<body>{body}</body>
</html>
"""


# Markdown conversion helper
try:
    import markdown as _md_mod

    def markdown_to_html(text: str) -> str:
        return _md_mod.markdown(text or "", extensions=["extra", "tables", "fenced_code"])
except Exception:
    _md_header_re = re.compile(r"^(#{1,6})\s+(.*)$")

    def markdown_to_html(text: str) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        out = []
        in_code = False
        for line in lines:
            if line.strip().startswith("```"):
                if not in_code:
                    in_code = True
                    out.append("<pre><code>")
                else:
                    in_code = False
                    out.append("</code></pre>")
                continue
            if in_code:
                out.append(html.escape(line) + "\n")
                continue
            m = _md_header_re.match(line)
            if m:
                level = len(m.group(1))
                out.append(f"<h{level}>{html.escape(m.group(2))}</h{level}>")
                continue
            esc = html.escape(line)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
            esc = re.sub(r"\*(.+?)\*", r"<em>\1</em>", esc)
            if esc.strip():
                out.append(f"<p>{esc}</p>")
        return "\n".join(out)


def fetch_url(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    logger.debug("Fetching %s %s (timeout=%s)", method, url, timeout)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            text = body.decode("utf-8", errors="replace")
            logger.debug(
                "Received response from %s with status %s and %d bytes",
                url,
                resp.getcode(),
                len(body),
            )
            try:
                result = {"status": resp.getcode(), "body": json.loads(text)}
                logger.debug("Parsed JSON response for %s", url)
                return result
            except Exception:
                logger.debug("Returning raw text body for %s", url)
                return {"status": resp.getcode(), "body": text}
    except urllib.error.HTTPError as he:
        try:
            body = he.read().decode("utf-8", errors="replace")
            snippet = body[:200]
            logger.warning("HTTP error %s for %s: %s", he.code, url, snippet)
            return {"status": he.code, "error": body}
        except Exception:
            logger.warning("HTTP error %s for %s (failed to read body)", he.code, url)
            return {"status": he.code, "error": str(he)}
    except Exception as e:
        logger.error("Unexpected error fetching %s: %s", url, e)
        return {"status": None, "error": str(e)}


def get_default_base_url() -> str:
    return os.getenv("CORTANA_BACKEND", "http://127.0.0.1:5500")


def backend_ask_raw(question: str) -> Dict[str, Any]:
    base_url = get_default_base_url()
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "ask")
    # TODO: Work on getting our actual applications listed by this
    payload = {
        "question": question,
        "geolocation": {"lat": 0.0, "lon": 0.0},
        "applications": ["Edge", "Spotify"],
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    logger.debug("Asking backend at %s with payload %s", url, payload)
    out = fetch_url(url, method="POST", data=data, headers=headers)
    logger.debug("Backend response: status=%s error=%s", out.get("status"), out.get("error"))
    if out.get("status") and isinstance(out.get("body"), dict):
        logger.debug("Backend returned body for question %s", question)
        return out["body"]
    error_value = out.get("error") or out.get("body")
    logger.warning("Backend returned error for question %s: %s", question, error_value)
    return {"error": error_value}



class AskWorker(QThread):
    finished_ok = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def run(self) -> None:
        logger.debug("AskWorker started for question: %s", self.question)
        try:
            raw = backend_ask_raw(self.question)
            if "error" in raw:
                logger.warning("AskWorker received backend error for %s: %s", self.question, raw["error"])
                self.finished_error.emit(str(raw["error"]))
                return

            md_src = raw.get("display_markdown") or ""
            display_html = markdown_to_html(md_src)

            result = {
                "question": raw.get("question"),
                "speech": raw.get("speech"),
                "display_markdown": md_src,
                "display_html": display_html,
                "url": raw.get("url"),
                "launch_app": raw.get("launch_app"),
                "cards": raw.get("cards") or [],
            }
            logger.debug(
                "AskWorker success for %s (%d cards)",
                self.question,
                len(result["cards"]),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            logger.error("AskWorker failed for %s: %s", self.question, e)
            self.finished_error.emit(str(e))

class App(QObject):
    """
    Compatibility wrapper for the phoneos app system.

    Usage: App(window, container)
    Creates the settings UI inside the provided `container` widget so the
    platform can host the app in its own window/layout (matching `main-old.py`).
    """
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self.worker: Optional[AskWorker] = None
        self.pending_question: Optional[str] = None
        self.active_animations: List[QParallelAnimationGroup] = []
        self._response_animating = False

        root = QWidget()
        root.setObjectName("RootWidget")

        main = QVBoxLayout(root)
        main.setContentsMargins(8,8,8,8)
        main.setSpacing(12)

        self.container.setLayout(main)

        self.cards_view = QWebEngineView()
        self.cards_view.setObjectName("CardsView")
        self.cards_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cards_view.setContextMenuPolicy(Qt.NoContextMenu)
        main.addWidget(self.cards_view, 1)

        self._current_cards: List[Dict[str, Any]] = []
        self._cards_css = ""

        self.response_view = QTextBrowser()
        self.response_view.setObjectName("ResponseView")
        self.response_view.setOpenExternalLinks(True)
        self.response_view.setPlaceholderText("No response yet.")
        self.response_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.response_view.setMinimumHeight(0)
        self.response_view.setMaximumHeight(0)
        self.response_view.document().contentsChanged.connect(self.update_response_view_height)
        self._set_widget_opacity(self.response_view, 0.0)
        main.addWidget(self.response_view)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        main.addLayout(input_row)

        self.question_input = styled_line_edit("Ask something...")
        self.question_input.returnPressed.connect(self.submit_question)
        input_row.addWidget(self.question_input, 1)

        self.ask_button = styled_button("Ask", primary=True)
        self.ask_button.clicked.connect(self.submit_question)
        input_row.addWidget(self.ask_button)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        main.addWidget(self.status_label)

        self.apply_styles()
        self.clear_cards()

    def apply_styles(self) -> None:
        theme = get_theme()
        panel = qcolor_css(theme.panel)
        panel2 = qcolor_css(theme.panel2)
        bg = qcolor_css(theme.bg)
        text = qcolor_css(theme.text)
        muted = qcolor_css(theme.muted)
        divider = qcolor_css(theme.divider)

        css = f"""
QWebEngineView#CardsView {{
    border: none;
    background: transparent;
}}
QTextBrowser#ResponseView {{
    background: {panel};
    border: 1px solid {divider};
    border-radius: 10px;
    padding: 8px;
    color: {text};
}}
QLabel#StatusLabel {{
    color: {muted};
    font-size: 13px;
}}
"""
        accent = qcolor_css(theme.accent)
        self._cards_css = f"""
* {{ box-sizing: border-box; }}
html, body {{
    margin: 0;
    padding: 0;
    background: {bg};
    color: {text};
    font-family: 'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif;
}}
body {{
    min-height: 100%;
    padding: 8px 8px 0px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}}
body {{
    scrollbar-width: none;
}}
body::-webkit-scrollbar {{
    width: 0;
    height: 0;
}}
body::-webkit-scrollbar-track,
body::-webkit-scrollbar-thumb {{
    background: transparent;
}}
.card {{
    background: {panel};
    border: 1px solid {divider};
    border-radius: 4px;
    padding: 14px;
}}
.card h2 {{
    margin: 0 0 12px;
    font-weight: 700;
    font-size: 18px;
}}
.card-body {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: flex-start;
}}
.card-img {{
    width: 120px;
    max-height: 200px;
    object-fit: cover;
    border-radius: 10px;
    flex-shrink: 0;
}}
.card-content {{
    flex: 1;
    min-width: 0;
}}
.desc {{
    margin-bottom: 10px;
    color: {muted};
    font-size: 12px;
}}
.kv {{
    margin-bottom: 6px;
    font-size: 14px;
}}
.kv strong {{
    font-weight: 600;
    color: {text};
}}
.card-body p {{
    margin: 0 0 6px;
    line-height: 1.4;
}}
.snippet {{
    margin-top: 4px;
    color: {muted};
    font-size: 13px;
}}
.news-list {{
    list-style: none;
    padding: 0;
    margin: 0;
}}
.news-item {{
    display: flex;
    gap: 12px;
    margin: 10px 0;
    align-items: flex-start;
}}
.thumb-wrap {{
    flex: 0 0 auto;
}}
.news-title {{
    font-weight: 600;
    font-size: 15px;
}}
.meta {{
    font-size: 12px;
    color: {muted};
    margin-top: 6px;
}}
.wx-main {{
    font-size: 20px;
    font-weight: 700;
    margin: 0 0 6px;
}}
.empty {{
    color: {muted};
    text-align: center;
    margin-top: 32px;
    font-size: 14px;
}}
a {{
    color: {accent};
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}
"""
        self._set_cards_html(self._current_cards, animate=False)
        self.container.setStyleSheet(css)

    def _track_animation(self, animation: QParallelAnimationGroup) -> None:
        self.active_animations.append(animation)

        def _cleanup() -> None:
            if animation in self.active_animations:
                self.active_animations.remove(animation)
            animation.deleteLater()

        animation.finished.connect(_cleanup)

    def _set_widget_opacity(self, widget: QWidget, opacity: float) -> QGraphicsOpacityEffect:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(opacity)
        return effect

    def _compose_cards_html(self, cards: List[Dict[str, Any]]) -> str:
        body = "".join(render_card_html(card) for card in cards)
        if not body:
            body = "<p class='empty'>Ask something to see cards.</p>"
        return CARD_PAGE_TEMPLATE.format(style=self._cards_css, body=body)

    def _set_cards_html(self, cards: List[Dict[str, Any]], animate: bool = False) -> None:
        self._current_cards = cards
        html = self._compose_cards_html(cards)
        self.cards_view.setHtml(html, QUrl("about:blank"))
        if animate and cards:
            self._animate_cards_in()
        elif cards:
            self._set_widget_opacity(self.cards_view, 1.0)

    def _animate_cards_in(self) -> None:
        effect = self._set_widget_opacity(self.cards_view, 0.0)
        group = QParallelAnimationGroup(self.window)
        fade = QPropertyAnimation(effect, b"opacity", group)
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)
        self._track_animation(group)
        group.start()

    def _set_response_height(self, height: int) -> None:
        height = max(0, height)
        self.response_view.setMinimumHeight(height)
        self.response_view.setMaximumHeight(height)

    def _shared_content_height(self) -> int:
        response_h = max(
            self.response_view.maximumHeight(),
            self.response_view.minimumHeight(),
            self.response_view.height(),
        )
        return max(120, self.cards_view.height() + response_h)

    def _minimum_visible_cards_height(self) -> int:
        return 0

    def _calculate_response_target_height(self) -> int:
        plain_text = self.response_view.toPlainText().strip()
        if not plain_text:
            return 0

        doc = self.response_view.document()
        view_w = self.response_view.viewport().width()
        if view_w <= 10:
            view_w = self.response_view.width()
        if view_w <= 10 and self.container() is not None:
            view_w = self.container().width() - 28
        view_w = max(10, view_w)

        doc.setTextWidth(view_w)
        content_height = int(doc.size().height()) + 12

        shared_h = self._shared_content_height()
        max_by_window = int(shared_h * 0.6)

        min_cards_area = self._minimum_visible_cards_height()
        max_by_cards = shared_h if min_cards_area <= 0 else max(0, shared_h - min_cards_area)

        max_target = min(max_by_window, max_by_cards)
        if max_target <= 0:
            return 0

        return min(content_height, max_target)

    def _start_request(self) -> None:
        question = (self.pending_question or "").strip()
        if not question:
            return

        self.worker = AskWorker(question)
        self.worker.finished_ok.connect(self.on_response_ok)
        self.worker.finished_error.connect(self.on_response_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def _animate_cards_out_and_start(self) -> None:
        has_response = bool(self.response_view.toPlainText().strip()) or self.response_view.maximumHeight() > 0
        has_cards = bool(self._current_cards)

        if not has_cards and not has_response:
            self.clear_cards()
            self.response_view.clear()
            self._set_response_height(0)
            self._set_widget_opacity(self.response_view, 0.0)
            self._start_request()
            return

        group = QParallelAnimationGroup(self.window)

        cards_effect = self._set_widget_opacity(self.cards_view, 1.0)
        fade_cards = QPropertyAnimation(cards_effect, b"opacity", group)
        fade_cards.setDuration(200)
        fade_cards.setStartValue(cards_effect.opacity())
        fade_cards.setEndValue(0.0)
        fade_cards.setEasingCurve(QEasingCurve.InCubic)
        group.addAnimation(fade_cards)

        if has_response:
            self._response_animating = True
            response_effect = self._set_widget_opacity(self.response_view, 1.0)

            fade = QPropertyAnimation(response_effect, b"opacity", group)
            fade.setDuration(180)
            fade.setStartValue(response_effect.opacity())
            fade.setEndValue(0.0)
            fade.setEasingCurve(QEasingCurve.InCubic)
            group.addAnimation(fade)

            collapse_min = QPropertyAnimation(self.response_view, b"minimumHeight", group)
            collapse_min.setDuration(220)
            collapse_min.setStartValue(self.response_view.minimumHeight)
            collapse_min.setEndValue(0)
            collapse_min.setEasingCurve(QEasingCurve.InCubic)
            group.addAnimation(collapse_min)

            collapse_max = QPropertyAnimation(self.response_view, b"maximumHeight", group)
            collapse_max.setDuration(220)
            collapse_max.setStartValue(self.response_view.maximumHeight)
            collapse_max.setEndValue(0)
            collapse_max.setEasingCurve(QEasingCurve.InCubic)
            group.addAnimation(collapse_max)

        def _after() -> None:
            self._response_animating = False
            self.clear_cards()
            self.response_view.clear()
            self._set_response_height(0)
            self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._set_widget_opacity(self.response_view, 0.0)
            self._start_request()

        group.finished.connect(_after)
        self._track_animation(group)
        group.start()

    def _animate_response_in(self) -> None:
        target_height = self._calculate_response_target_height()
        if target_height <= 0:
            self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._set_response_height(0)
            self._set_widget_opacity(self.response_view, 0.0)
            return

        self._response_animating = True
        self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._set_response_height(0)
        effect = self._set_widget_opacity(self.response_view, 0.0)

        group = QParallelAnimationGroup(self.window)

        fade = QPropertyAnimation(effect, b"opacity", group)
        fade.setDuration(240)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)

        grow_min = QPropertyAnimation(self.response_view, b"minimumHeight", group)
        grow_min.setDuration(320)
        grow_min.setStartValue(0)
        grow_min.setEndValue(target_height)
        grow_min.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(grow_min)

        grow_max = QPropertyAnimation(self.response_view, b"maximumHeight", group)
        grow_max.setDuration(320)
        grow_max.setStartValue(0)
        grow_max.setEndValue(target_height)
        grow_max.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(grow_max)

        def _after() -> None:
            self._response_animating = False
            self.update_response_view_height()

        group.finished.connect(_after)
        self._track_animation(group)
        group.start()

    def clear_cards(self) -> None:
        logger.debug("Clearing existing cards (count=%d)", len(self._current_cards))
        self._set_cards_html([], animate=False)
        self._set_widget_opacity(self.cards_view, 0.0)
        self.update_response_view_height()

    def submit_question(self) -> None:
        self.clear_cards()
        question = self.question_input.text().strip()
        if not question:
            return
        logger.debug("Submitting question: %s", question)

        self.ask_button.setDisabled(True)
        self.question_input.setDisabled(True)
        self.status_label.setText("Loading...")
        self.pending_question = question
        self._animate_cards_out_and_start()

    def on_response_ok(self, data: Dict[str, Any]) -> None:
        cards = data.get("cards") or []
        logger.debug(
            "Response OK: %d cards, url=%s, launch_app=%s",
            len(cards),
            data.get("url"),
            data.get("launch_app"),
        )
        self._set_cards_html(cards, animate=bool(cards))

        parts = []
        display_html = data.get("display_html")
        if display_html:
            parts.append(display_html)
        elif data.get("display_markdown"):
            parts.append(f"<p>{html.escape(data['display_markdown'])}</p>")

        if data.get("url"):
            safe_url = html.escape(str(data["url"]), quote=True)
            QMessageBox.information(title="Launch URL", text=f"Would open URL {safe_url}")
            # parts.append(f'<p><a href="{safe_url}">{safe_url}</a></p>')

        if data.get("launch_app"):
            QMessageBox.information(title="Launch URL", text=f"Would launch app {str(data['launch_app'])}")
            # parts.append(f"<p><strong>Launch App:</strong> {html.escape(str(data['launch_app']))}</p>")

        self.response_view.setHtml("".join(parts) or "<p>(No content)</p>")
        self._animate_response_in()

        speech = data.get("speech") or ""
        self.status_label.setText(f"TTS: {speech}" if speech else "Done.")

    def on_response_error(self, error_text: str) -> None:
        logger.error("Response error displayed: %s", error_text)
        self.clear_cards()
        self.response_view.setHtml(
            f'<p style="color:#ff7b7b;"><strong>Error:</strong> {html.escape(error_text)}</p>'
        )
        self._animate_response_in()
        self.status_label.setText("Request failed.")

    def on_worker_finished(self) -> None:
        logger.debug("AskWorker finished; resetting UI")
        self.ask_button.setDisabled(False)
        self.question_input.setDisabled(False)
        self.question_input.clear()
        self.question_input.setFocus()
        self.pending_question = None
        self.update_response_view_height()

    def update_response_view_height(self) -> None:
        try:
            if not hasattr(self, "response_view") or self._response_animating:
                return

            target_height = self._calculate_response_target_height()
            self._set_response_height(target_height)

            if target_height <= 0:
                self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self._set_widget_opacity(self.response_view, 0.0)
                return

            doc = self.response_view.document()
            view_w = max(10, self.response_view.viewport().width())
            doc.setTextWidth(view_w)
            content_height = int(doc.size().height()) + 12

            if content_height > target_height:
                self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            else:
                self.response_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._set_widget_opacity(self.response_view, 1.0)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_response_view_height()

def main() -> int:
    app = QApplication(sys.argv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())