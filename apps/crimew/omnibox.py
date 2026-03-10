from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import requests

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot, QStringListModel, Qt
from PySide6.QtWidgets import QCompleter, QLineEdit

from input_helper import VIRTUAL_KEYBOARD_CLOSE_ON_ENTER_PROPERTY, VIRTUAL_KEYBOARD_PERSISTENT_PROPERTY

import autocomplete
from dataclasses import dataclass
from PySide6.QtCore import QAbstractListModel, QModelIndex
from PySide6.QtGui import QFont, QFontMetrics, QColor
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

_SEARCH_URLS: dict[str, str] = {
	"google": "https://www.google.com/search?q={query}",
	"bing": "https://www.bing.com/search?q={query}",
	"duckduckgo": "https://duckduckgo.com/?q={query}",
}


def search_url_for_query(query: str, provider: str) -> QUrl:
	safe_provider = provider if provider in _SEARCH_URLS else "google"
	template = _SEARCH_URLS[safe_provider]
	encoded = QUrl.toPercentEncoding(query).data().decode("ascii")
	return QUrl(template.format(query=encoded))


def resolve_omnibox_input(text: str, provider: str) -> QUrl:
	value = (text or "").strip()
	if not value:
		return QUrl()

	if _looks_like_url(value):
		return QUrl.fromUserInput(value)

	return search_url_for_query(value, provider)


def _looks_like_url(value: str) -> bool:
	lowered = value.lower()
	if any(lowered.startswith(prefix) for prefix in ("http://", "https://", "file://", "about:", "chrome://")):
		return True

	if " " in value:
		return False

	if lowered.startswith("localhost"):
		return True

	if "." in value:
		return True

	return False


@dataclass
class _SuggestionRequest:
	request_id: int
	provider: str
	query: str


class _SuggestionEmitter(QObject):
	suggestions_ready = Signal(int, list)


class _SuggestionTask(QRunnable):
	def __init__(self, request: _SuggestionRequest, emitter: _SuggestionEmitter):
		super().__init__()
		self._request = request
		self._emitter = emitter

	def run(self):
		suggestions = _fetch_suggestions(self._request.provider, self._request.query)
		self._emitter.suggestions_ready.emit(self._request.request_id, suggestions)


def _fetch_suggestions(provider: str, query: str) -> list[str]:
	if not query:
		return []

	try:
		if provider == "google":
			raw = autocomplete.autocomplete(query, include_kg=False)
			return [s for s in raw if isinstance(s, str)]

		if provider == "bing":
			resp = requests.get(
				"https://api.bing.com/osjson.aspx",
				params={"query": query},
				timeout=3,
			)
			resp.raise_for_status()
			data = resp.json()
			if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
				return [s for s in data[1] if isinstance(s, str)]

		if provider == "duckduckgo":
			resp = requests.get(
				"https://duckduckgo.com/ac/",
				params={"q": query, "type": "list"},
				timeout=3,
			)
			resp.raise_for_status()
			data = resp.json()
			if isinstance(data, list):
				out = []
				for item in data:
					if isinstance(item, dict):
						phrase = item.get("phrase")
						if isinstance(phrase, str):
							out.append(phrase)
				return out
	except Exception:
		return []

	return []


class Omnibox(QLineEdit):
	navigate_requested = Signal(QUrl)

	def __init__(self, get_search_provider: Callable[[], str], parent=None):
		super().__init__(parent)
		# Keep the on-screen keyboard alive while suggestions are shown
		# so that interacting with the completer doesn't dismiss it.
		self.setProperty(VIRTUAL_KEYBOARD_PERSISTENT_PROPERTY, True)
		self.setProperty(VIRTUAL_KEYBOARD_CLOSE_ON_ENTER_PROPERTY, True)
		self._get_search_provider = get_search_provider
		self._request_id = 0

		self._model = QStringListModel(self)
		self._completer = QCompleter(self._model, self)
		self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
		self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
		self._completer.setCompletionMode(QCompleter.PopupCompletion)
		self.setCompleter(self._completer)

		self._debounce_timer = QTimer(self)
		self._debounce_timer.setSingleShot(True)
		self._debounce_timer.setInterval(200)
		self._debounce_timer.timeout.connect(self._request_suggestions)

		self._emitter = _SuggestionEmitter()
		self._emitter.suggestions_ready.connect(self._on_suggestions_ready)

		self._thread_pool = QThreadPool.globalInstance()

		self.textEdited.connect(self._on_text_edited)
		self.returnPressed.connect(self._on_return_pressed)
		self._completer.activated.connect(self._on_completion_activated)

	@Slot(str)
	def _on_text_edited(self, text: str):
		if len(text.strip()) < 2:
			self._model.setStringList([])
			self._completer.popup().hide()
			return
		self._debounce_timer.start()

	@Slot()
	def _request_suggestions(self):
		query = self.text().strip()
		if len(query) < 2:
			self._model.setStringList([])
			return

		self._request_id += 1
		request = _SuggestionRequest(
			request_id=self._request_id,
			provider=self._get_search_provider(),
			query=query,
		)
		self._thread_pool.start(_SuggestionTask(request, self._emitter))

	@Slot(int, list)
	def _on_suggestions_ready(self, request_id: int, suggestions: list):
		if request_id != self._request_id:
			return

		current_text = self.text().strip()
		cleaned = [s for s in suggestions if isinstance(s, str) and s.strip()]
		self._model.setStringList(cleaned[:12])

		if len(current_text) < 2 or not cleaned:
			self._completer.popup().hide()
			return

		self._completer.setCompletionPrefix(current_text)
		self._completer.complete()

	@Slot(str)
	def _on_completion_activated(self, text: str):
		self.setText(text)
		self._on_return_pressed()

	@Slot()
	def _on_return_pressed(self):
		provider = self._get_search_provider()
		url = resolve_omnibox_input(self.text(), provider)
		if url.isValid() and not url.isEmpty():
			self.navigate_requested.emit(url)
