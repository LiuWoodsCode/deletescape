from __future__ import annotations

from audio import (
    AudioDevice,
    AudioInfo,
    get_audio_info,
    list_audio_output_devices,
    set_muted,
    set_output_device,
    set_volume,
)

from ._runtime import bind_window


def info() -> AudioInfo:
    return get_audio_info()


def get_info() -> AudioInfo:
    return get_audio_info()


def list_output_devices() -> list[AudioDevice]:
    return list_audio_output_devices()


__all__ = [
    "AudioDevice",
    "AudioInfo",
    "bind_window",
    "get_audio_info",
    "get_info",
    "info",
    "list_audio_output_devices",
    "list_output_devices",
    "set_muted",
    "set_output_device",
    "set_volume",
]