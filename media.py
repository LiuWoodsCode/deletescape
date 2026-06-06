from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal


MEDIA_COMMANDS = {
    "play",
    "pause",
    "toggle_play_pause",
    "stop",
    "previous",
    "next",
    "seek_backward",
    "seek_forward",
    "seek_to",
    "rewind",
    "fast_forward",
}

PLAYBACK_STATES = {"playing", "paused", "stopped", "buffering"}


@dataclass(frozen=True)
class MediaSession:
    app_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    artwork_path: str = ""
    position_ms: int | None = None
    duration_ms: int | None = None
    playback_state: str = "playing"
    updated_at: float = field(default_factory=time.time)
    available_commands: tuple[str, ...] = ()

    def supports(self, command: str) -> bool:
        command = _normalize_command(command)
        return "*" in self.available_commands or command in self.available_commands


def _normalize_command(command: str) -> str:
    command = str(command or "").strip().lower().replace("-", "_")
    if command == "rewind":
        return "seek_backward"
    if command == "fast_forward":
        return "seek_forward"
    return command


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except Exception:
        return None


def _invoke_callback(callback: Callable[..., Any], *, command: str, payload: dict[str, Any], generic: bool) -> None:
    attempts = []
    if generic:
        attempts.extend((
            lambda: callback(command, **payload),
            lambda: callback(command),
            lambda: callback(),
        ))
    else:
        attempts.extend((
            lambda: callback(**payload),
            lambda: callback(),
        ))

    last_type_error: TypeError | None = None
    for attempt in attempts:
        try:
            attempt()
            return
        except TypeError as exc:
            last_type_error = exc
            continue

    if last_type_error is not None:
        raise last_type_error


class MediaSessionManager(QObject):
    session_changed = Signal(object)
    command_requested = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._sessions: dict[str, MediaSession] = {}
        self._callbacks: dict[str, dict[str, Callable[..., Any]]] = {}
        self._session_order: list[str] = []

    def set_session(
        self,
        *,
        app_id: str,
        title: str = "",
        artist: str = "",
        album: str = "",
        artwork_path: str = "",
        position_ms: int | None = None,
        duration_ms: int | None = None,
        playback_state: str = "playing",
        controls: dict[str, Callable[..., Any]] | None = None,
    ) -> MediaSession:
        app_id = str(app_id or "").strip()
        if not app_id:
            raise ValueError("app_id is required for a media session")

        playback_state = str(playback_state or "playing").strip().lower()
        if playback_state not in PLAYBACK_STATES:
            playback_state = "playing"

        if controls is not None:
            callbacks: dict[str, Callable[..., Any]] = {}
            for raw_command, callback in controls.items():
                command = _normalize_command(raw_command)
                if command in {"*", "on_command"}:
                    command = "*"
                if not callable(callback):
                    continue
                if command == "*" or command in MEDIA_COMMANDS:
                    callbacks[command] = callback
            self._callbacks[app_id] = callbacks

        available_commands = tuple(sorted(self._callbacks.get(app_id, {}).keys()))
        session = MediaSession(
            app_id=app_id,
            title=str(title or ""),
            artist=str(artist or ""),
            album=str(album or ""),
            artwork_path=str(artwork_path or ""),
            position_ms=_coerce_optional_int(position_ms),
            duration_ms=_coerce_optional_int(duration_ms),
            playback_state=playback_state,
            updated_at=time.time(),
            available_commands=available_commands,
        )

        self._sessions[app_id] = session
        if app_id in self._session_order:
            self._session_order.remove(app_id)
        self._session_order.append(app_id)
        self.session_changed.emit(self.active_session())
        return session

    def clear_session(self, app_id: str) -> None:
        app_id = str(app_id or "").strip()
        if not app_id:
            return
        changed = app_id in self._sessions
        self._sessions.pop(app_id, None)
        self._callbacks.pop(app_id, None)
        if app_id in self._session_order:
            self._session_order.remove(app_id)
        if changed:
            self.session_changed.emit(self.active_session())

    def active_session(self) -> MediaSession | None:
        for app_id in reversed(self._session_order):
            session = self._sessions.get(app_id)
            if session is not None and session.playback_state == "playing":
                return session

        for app_id in reversed(self._session_order):
            session = self._sessions.get(app_id)
            if session is not None and session.playback_state != "stopped":
                return session

        return None

    def dispatch_command(self, command: str, *, app_id: str | None = None, **payload: Any) -> bool:
        command = _normalize_command(command)
        if command not in MEDIA_COMMANDS:
            return False

        if app_id is None:
            session = self.active_session()
            app_id = session.app_id if session is not None else None

        app_id = str(app_id or "").strip()
        if not app_id:
            return False

        callbacks = self._callbacks.get(app_id, {})
        callback = callbacks.get(command)
        generic = False
        if callback is None:
            callback = callbacks.get("*")
            generic = callback is not None
        if callback is None:
            return False

        self.command_requested.emit(app_id, command)
        _invoke_callback(callback, command=command, payload=payload, generic=generic)
        return True
