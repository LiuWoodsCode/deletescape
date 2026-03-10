from __future__ import annotations

from audio import AudioDriverBase, AudioInfo
from logger import get_logger


log = get_logger("drivers.audio.none")


class NoneAudioDriver(AudioDriverBase):
    def get_audio_info(self) -> AudioInfo:
        log.debug("Audio none driver get_audio_info requested")
        return AudioInfo(
            volume_percent=None,
            muted=None,
            output_route=None,
            driver="none",
        )

    def set_volume(self, percent: int) -> bool:
        log.info("Audio none driver set_volume rejected", extra={"percent": int(percent)})
        return False

    def set_muted(self, muted: bool) -> bool:
        log.info("Audio none driver set_muted rejected", extra={"muted": bool(muted)})
        return False


def create_audio_driver() -> AudioDriverBase:
    log.info("Audio none driver created")
    return NoneAudioDriver()
