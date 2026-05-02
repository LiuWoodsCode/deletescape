from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class App:
    def __init__(self, window, container: QWidget):
        self.window = window
        self.container = container
        self.app_id = "mediaplayer"
        self._current_path: Path | None = None
        self._duration_ms = 0
        self._slider_is_pressed = False
        self._session_timer = QTimer(container)
        self._session_timer.timeout.connect(self._publish_media_session)
        self._session_timer.setInterval(1000)

        self.player = QMediaPlayer(container)
        self.audio_output = QAudioOutput(container)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)

        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(10)

        self.video = QVideoWidget(container)
        self.video.setMinimumHeight(220)
        self.video.setStyleSheet("background-color: black;")
        self.player.setVideoOutput(self.video)
        self.layout.addWidget(self.video, 1)

        self.title_label = QLabel("No media loaded")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.layout.addWidget(self.title_label)

        self.status_label = QLabel("Open an audio or video file to start playback.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.layout.addWidget(self.position_slider)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setAlignment(Qt.AlignRight)
        self.layout.addWidget(self.time_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.layout.addLayout(controls)

        self.open_btn = QPushButton("Open")
        self.rewind_btn = QPushButton("-10s")
        self.play_btn = QPushButton("Play")
        self.forward_btn = QPushButton("+10s")
        self.stop_btn = QPushButton("Stop")

        controls.addWidget(self.open_btn)
        controls.addStretch(1)
        controls.addWidget(self.rewind_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.forward_btn)
        controls.addWidget(self.stop_btn)

        self.open_btn.clicked.connect(self._open_file_dialog)
        self.rewind_btn.clicked.connect(lambda: self._seek_relative(-10000))
        self.play_btn.clicked.connect(self._toggle_play_pause)
        self.forward_btn.clicked.connect(lambda: self._seek_relative(10000))
        self.stop_btn.clicked.connect(self._stop)

        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)

        self._set_controls_enabled(False)

        try:
            self.window.enable_background(True)
        except Exception:
            pass

        initial = self._consume_open_intent()
        if initial is not None:
            self._load_file(initial, autoplay=True)

    def _consume_open_intent(self) -> Path | None:
        try:
            intent_path = (
                Path(__file__).resolve().parents[2]
                / "userdata"
                / "Data"
                / "Application"
                / self.app_id
                / "open_intent.json"
            )
            if not intent_path.exists():
                return None

            try:
                data = json.loads(intent_path.read_text(encoding="utf-8"))
                raw_path = data.get("path")
            finally:
                try:
                    intent_path.unlink()
                except Exception:
                    pass

            if raw_path:
                path = Path(raw_path)
                if path.exists():
                    return path
        except Exception:
            pass
        return None

    def _open_file_dialog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self.container,
            "Open Media",
            str(Path.home()),
            "Media Files (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.mp4 *.m4v *.mov *.webm *.mkv *.avi);;All Files (*)",
        )
        if not path:
            return
        self._load_file(Path(path), autoplay=True)

    def _load_file(self, path: Path, *, autoplay: bool = False) -> None:
        self._current_path = path
        self._duration_ms = 0
        self.title_label.setText(path.stem)
        self.status_label.setText(path.name)
        self.position_slider.setRange(0, 0)
        self.time_label.setText("0:00 / 0:00")
        self._set_controls_enabled(True)

        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self._publish_media_session(playback_state="paused")

        if autoplay:
            self.player.play()

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.play_btn.setEnabled(enabled)
        self.rewind_btn.setEnabled(enabled)
        self.forward_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.position_slider.setEnabled(enabled)

    def _toggle_play_pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _play(self) -> None:
        self.player.play()

    def _pause(self) -> None:
        self.player.pause()

    def _stop(self) -> None:
        self.player.stop()
        self._publish_media_session(playback_state="stopped")

    def _seek_relative(self, offset_ms: int = 0) -> None:
        if not self._current_path:
            return
        current = int(self.player.position())
        duration = int(self._duration_ms or self.player.duration() or 0)
        target = max(0, current + int(offset_ms or 0))
        if duration:
            target = min(duration, target)
        self.player.setPosition(target)
        self._publish_media_session()

    def _seek_backward(self, offset_ms: int = 10000) -> None:
        self._seek_relative(-abs(int(offset_ms or 10000)))

    def _seek_forward(self, offset_ms: int = 10000) -> None:
        self._seek_relative(abs(int(offset_ms or 10000)))

    def _seek_to(self, position_ms: int = 0) -> None:
        if not self._current_path:
            return
        duration = int(self._duration_ms or self.player.duration() or 0)
        target = max(0, int(position_ms or 0))
        if duration:
            target = min(duration, target)
        self.player.setPosition(target)
        self._publish_media_session()

    def _on_slider_pressed(self) -> None:
        self._slider_is_pressed = True

    def _on_slider_released(self) -> None:
        self._slider_is_pressed = False
        self.player.setPosition(self.position_slider.value())
        self._publish_media_session()

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms or 0))
        self.position_slider.setRange(0, self._duration_ms)
        self._update_time_label()
        self._publish_media_session()

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._slider_is_pressed:
            self.position_slider.setValue(max(0, int(position_ms or 0)))
        self._update_time_label()

    def _on_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("Pause")
            self.status_label.setText(self._current_path.name if self._current_path else "Playing")
            self._session_timer.start()
        elif state == QMediaPlayer.PausedState:
            self.play_btn.setText("Play")
            self._session_timer.stop()
        else:
            self.play_btn.setText("Play")
            self._session_timer.stop()
        self._publish_media_session()

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self._publish_media_session(playback_state="stopped")

    def _on_error(self, error, error_string: str = "") -> None:
        if not error:
            return
        message = str(error_string or "Could not play this file.")
        self.status_label.setText(message)
        try:
            self.window.notify(title="Media Player", message=message, duration_ms=3500, app_id=self.app_id)
        except Exception:
            pass

    def _update_time_label(self) -> None:
        position = int(self.player.position() or 0)
        duration = int(self._duration_ms or self.player.duration() or 0)
        self.time_label.setText(f"{self._format_ms(position)} / {self._format_ms(duration)}")

    def _format_ms(self, value: int) -> str:
        total = max(0, int(value or 0) // 1000)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _playback_state_name(self) -> str:
        state = self.player.playbackState()
        if state == QMediaPlayer.PlayingState:
            return "playing"
        if state == QMediaPlayer.PausedState:
            return "paused"
        return "stopped"

    def _publish_media_session(self, *, playback_state: str | None = None) -> None:
        if self._current_path is None:
            return

        state = playback_state or self._playback_state_name()
        try:
            self.window.set_media_session(
                app_id=self.app_id,
                title=self._current_path.stem,
                artist="",
                album="",
                artwork_path="",
                position_ms=int(self.player.position() or 0),
                duration_ms=int(self._duration_ms or self.player.duration() or 0) or None,
                playback_state=state,
                controls={
                    "play": self._play,
                    "pause": self._pause,
                    "toggle_play_pause": self._toggle_play_pause,
                    "stop": self._stop,
                    "seek_backward": self._seek_backward,
                    "seek_forward": self._seek_forward,
                    "seek_to": self._seek_to,
                },
            )
        except Exception:
            pass

    def on_resume(self) -> None:
        self._publish_media_session()

    def on_pause(self) -> None:
        self._publish_media_session()

    def on_quit(self) -> None:
        try:
            self._session_timer.stop()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.window.clear_media_session(app_id=self.app_id)
        except Exception:
            pass
