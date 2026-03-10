from __future__ import annotations

from audio import AudioDriverBase, AudioInfo
from logger import get_logger


log = get_logger("drivers.audio.simulated")


class SimulatedAudioDriver(AudioDriverBase):
    def __init__(self):
        self._volume_percent = 48
        self._muted = False
        self._output_route = "speaker"
        log.info("Simulated audio driver initialized")

    def get_audio_info(self) -> AudioInfo:
        log.debug(
            "Simulated audio get_audio_info",
            extra={
                "volume_percent": self._volume_percent,
                "muted": self._muted,
                "output_route": self._output_route,
            },
        )
        return AudioInfo(
            volume_percent=self._volume_percent,
            muted=self._muted,
            output_route=self._output_route,
            driver="simulated",
        )

    def set_volume(self, percent: int) -> bool:
        self._volume_percent = max(0, min(100, int(percent)))
        if self._volume_percent > 0:
            self._muted = False
        log.info("Simulated audio volume set", extra={"volume_percent": self._volume_percent})
        return True

    def set_muted(self, muted: bool) -> bool:
        self._muted = bool(muted)
        log.info("Simulated audio mute set", extra={"muted": self._muted})
        return True


def create_audio_driver() -> AudioDriverBase:
    log.info("Creating simulated audio driver")
    return SimulatedAudioDriver()
