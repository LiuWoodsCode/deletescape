from __future__ import annotations

from typing import Any

from media import MediaSession

from ._runtime import bind_window, call_window_method


def set_now_playing(
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    artwork_path: str = "",
    position_ms: int | None = None,
    duration_ms: int | None = None,
    playback_state: str = "playing",
    controls: dict | None = None,
    app_id: str | None = None,
) -> MediaSession | None:
    return call_window_method(
        "set_media_session",
        title=title,
        artist=artist,
        album=album,
        artwork_path=artwork_path,
        position_ms=position_ms,
        duration_ms=duration_ms,
        playback_state=playback_state,
        controls=controls,
        app_id=app_id,
        required=True,
    )


def update_now_playing(**kwargs: Any) -> MediaSession | None:
    return set_now_playing(**kwargs)


def clear_now_playing(*, app_id: str | None = None) -> None:
    call_window_method("clear_media_session", app_id=app_id, required=True)


def get_now_playing() -> MediaSession | None:
    return call_window_method("get_active_media_session", default=None)


def send_command(command: str, *, app_id: str | None = None, **payload: Any) -> bool:
    return bool(call_window_method("send_media_command", command, app_id=app_id, default=False, **payload))


def play(*, app_id: str | None = None) -> bool:
    return send_command("play", app_id=app_id)


def pause(*, app_id: str | None = None) -> bool:
    return send_command("pause", app_id=app_id)


def toggle_play_pause(*, app_id: str | None = None) -> bool:
    return send_command("toggle_play_pause", app_id=app_id)


def stop(*, app_id: str | None = None) -> bool:
    return send_command("stop", app_id=app_id)


def previous(*, app_id: str | None = None) -> bool:
    return send_command("previous", app_id=app_id)


def next_track(*, app_id: str | None = None) -> bool:
    return send_command("next", app_id=app_id)


def seek_backward(*, app_id: str | None = None, milliseconds: int | None = None) -> bool:
    payload: dict[str, Any] = {}
    if milliseconds is not None:
        payload["milliseconds"] = int(milliseconds)
    return send_command("seek_backward", app_id=app_id, **payload)


def seek_forward(*, app_id: str | None = None, milliseconds: int | None = None) -> bool:
    payload: dict[str, Any] = {}
    if milliseconds is not None:
        payload["milliseconds"] = int(milliseconds)
    return send_command("seek_forward", app_id=app_id, **payload)


def seek_to(position_ms: int, *, app_id: str | None = None) -> bool:
    return send_command("seek_to", app_id=app_id, position_ms=int(position_ms))


__all__ = [
    "MediaSession",
    "bind_window",
    "clear_now_playing",
    "get_now_playing",
    "next_track",
    "pause",
    "play",
    "previous",
    "seek_backward",
    "seek_forward",
    "seek_to",
    "send_command",
    "set_now_playing",
    "stop",
    "toggle_play_pause",
    "update_now_playing",
]