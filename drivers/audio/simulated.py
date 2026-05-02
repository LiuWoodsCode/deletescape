from __future__ import annotations

from audio import AudioDevice, AudioDriverBase, AudioInfo
from logger import get_logger


log = get_logger("drivers.audio.simulated")


class SimulatedAudioDriver(AudioDriverBase):
    def __init__(self):
        self._volume_percent = 48
        self._muted = False
        self._devices = [
            AudioDevice(id="speaker", name="Speaker", description="Phone speaker", is_default=True),
            AudioDevice(id="headphones", name="Headphones", description="Wired headphones", is_default=False),
            AudioDevice(id="bluetooth", name="Bluetooth", description="Bluetooth audio", is_default=False),
        ]
        self._output_device_id = "speaker"
        log.info("Simulated audio driver initialized")

    def get_audio_info(self) -> AudioInfo:
        log.debug(
            "Simulated audio get_audio_info",
            extra={
                "volume_percent": self._volume_percent,
                "muted": self._muted,
                "output_device_id": self._output_device_id,
            },
        )
        active = self._active_device()
        return AudioInfo(
            volume_percent=self._volume_percent,
            muted=self._muted,
            output_route=(active.description or active.name),
            output_device_id=active.id,
            output_device_name=(active.description or active.name),
            output_devices=tuple(self.list_output_devices()),
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

    def list_output_devices(self) -> list[AudioDevice]:
        return [
            AudioDevice(
                id=device.id,
                name=device.name,
                description=device.description,
                is_default=(device.id == self._output_device_id),
            )
            for device in self._devices
        ]

    def set_output_device(self, device_id: str) -> bool:
        clean_id = str(device_id or "").strip()
        if not any(device.id == clean_id for device in self._devices):
            log.info("Simulated audio output device rejected", extra={"device_id": clean_id})
            return False
        self._output_device_id = clean_id
        log.info("Simulated audio output device set", extra={"device_id": clean_id})
        return True

    def _active_device(self) -> AudioDevice:
        for device in self.list_output_devices():
            if device.id == self._output_device_id:
                return device
        return self.list_output_devices()[0]


def create_audio_driver() -> AudioDriverBase:
    log.info("Creating simulated audio driver")
    return SimulatedAudioDriver()
