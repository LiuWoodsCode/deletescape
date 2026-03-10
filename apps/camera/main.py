from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os

from PySide6.QtCore import QEvent, QObject, Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QSizePolicy,
    QToolButton,
)

# Qt Multimedia (PySide6 >= 6.4 recommended)
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QImageCapture,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QVideoWidget

from photo_picker import get_default_dcim_dir
from config import ConfigStore, OSConfig, DeviceConfigStore, DeviceConfig
from logger import get_logger
import piexif

log = get_logger("camera")


class App(QObject):
    """
    Camera App

    - Matches structure/pattern of your Gallery App (App(window, container)).
    - Live preview via QVideoWidget + QMediaCaptureSession + QCamera.
    - Capture stills to DCIM with timestamp-based filenames.
    - Optional: write open_intent.json for Gallery to auto-open the last photo.
    """

    def __init__(self, window, container: QWidget):
        super().__init__(container)
        self.window = window
        self.container = container

        self._dcim_dir: Path = get_default_dcim_dir() 
        try:
            self._dcim_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.warning(f"Failed to ensure DCIM dir: {e}")

        # State
        self._camera: QCamera | None = None
        self._capture_session: QMediaCaptureSession | None = None
        self._image_capture: QImageCapture | None = None
        self._last_saved: Path | None = None
        self._view: str = "camera"  # keep parity with "grid|preview" idea
        self._starting_up: bool = False

        # Layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        self.container.setLayout(self.layout)
        self.container.installEventFilter(self)

        self._init_ui()
        self._init_media()
        self._start_camera_if_available()

    # ---------- UI ----------
    def _exif_dt(self, dt: datetime | None = None) -> str:
        """EXIF datetime string format."""
        dt = dt or datetime.now()
        return dt.strftime("%Y:%m:%d %H:%M:%S")

    def _encode_xp(self, s: str) -> bytes:
        """
        Encode for EXIF XP* tags (XPComment/XPKeywords/etc).
        XP tags use UTF-16LE and are typically null-terminated.
        """
        if not s:
            return b""
        return (s + "\x00").encode("utf-16le")

    def _attach_standard_exif(
        self,
        jpg_path: Path,
        *,
        description: str | None = None,
        comment: str | None = None,
        keywords: list[str] | None = None,
        artist: str | None = None,
        copyright_notice: str | None = None,
        software: str = "deletescapeOS Camera",
    ):
        """
        Write metadata into standard EXIF tags (no JSON payloads).
        """
        try:
            if jpg_path.suffix.lower() not in {".jpg", ".jpeg"}:
                log.debug(f"Skipping EXIF write for non-JPEG: {jpg_path}")
                return

            exif = piexif.load(str(jpg_path))  # preserves existing EXIF if present

            dt = self._exif_dt()

            # ---- Identify camera/device (best-effort)
            device_config_store = DeviceConfigStore()
            device: DeviceConfig = device_config_store.load()
            log.debug(
                "DeviceConfig loaded",
                extra={
                    "manufacturer": str(getattr(device, "manufacturer", "")),
                    "model": str(getattr(device, "model_name", "")),
                },
            )

            make = str(getattr(device, "manufacturer", ""))
            model = str(getattr(device, "model_name", ""))
            body_serial = None

            if self._camera and self._camera.cameraDevice().isNull() is False:
                dev = self._camera.cameraDevice()
                try:
                    body_serial = bytes(dev.id()).decode("utf-8", errors="ignore")
                    lens = dev.description() or None
                except Exception:
                    body_serial = str(dev.id()) if dev.id() else None

            # ---- 0th IFD (basic image tags)
            if make:
                exif["0th"][piexif.ImageIFD.Make] = make.encode("utf-8")
            if model:
                exif["0th"][piexif.ImageIFD.Model] = model.encode("utf-8")
            if lens:
                exif["Exif"][piexif.ExifIFD.LensModel] = lens.encode("utf-8")
            
            exif["0th"][piexif.ImageIFD.Software] = software.encode("utf-8")
            exif["0th"][piexif.ImageIFD.DateTime] = dt.encode("ascii")

            if artist:
                exif["0th"][piexif.ImageIFD.Artist] = artist.encode("utf-8")

            if copyright_notice:
                exif["0th"][piexif.ImageIFD.Copyright] = copyright_notice.encode("utf-8")

            if description:
                exif["0th"][piexif.ImageIFD.ImageDescription] = description.encode("utf-8")

            # Windows-friendly comment/keywords (still standard EXIF tags)
            if comment:
                exif["0th"][piexif.ImageIFD.XPComment] = self._encode_xp(comment)

            if keywords:
                # Common delimiter for XPKeywords is semicolon
                exif["0th"][piexif.ImageIFD.XPKeywords] = self._encode_xp(";".join(keywords))

            # ---- Exif IFD (capture-specific tags)
            exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt.encode("ascii")
            exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt.encode("ascii")

            if artist:
                # Many pipelines treat this as the operator/owner field
                exif["Exif"][piexif.ExifIFD.CameraOwnerName] = artist.encode("utf-8")

            if body_serial:
                exif["Exif"][piexif.ExifIFD.BodySerialNumber] = body_serial.encode("utf-8")

            # Write back
            piexif.insert(piexif.dump(exif), str(jpg_path))
            log.debug(f"Standard EXIF written: {jpg_path.name}")

        except Exception as e:
            log.warning(f"Failed writing EXIF: {e}")

    def _init_ui(self):
        self._clear_layout()

        # Title
        title = QLabel("Camera")
        title.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(title)

        # Preview area (video widget inside a scroll area for consistency / resilience)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.layout.addWidget(self.preview_scroll, 1)

        self.preview_host = QWidget()
        ph_layout = QVBoxLayout()
        ph_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_host.setLayout(ph_layout)
        self.preview_scroll.setWidget(self.preview_host)

        self.video_widget = QVideoWidget()
        # Allow it to shrink below the video’s intrinsic size so it can adapt to container
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setMinimumSize(QSize(160, 120))
        ph_layout.addWidget(self.video_widget)

        # Device + controls row
        controls = QHBoxLayout()

        # Camera selector
        self.device_combo = QComboBox()
        self.device_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        controls.addWidget(QLabel("Camera:"))
        controls.addWidget(self.device_combo, 1)

        # Capture button
        self.capture_btn = QPushButton("Shutter")
        self.capture_btn.setIcon(QIcon.fromTheme("camera-photo"))
        self.capture_btn.clicked.connect(self._on_capture_clicked)
        controls.addWidget(self.capture_btn)

        # "Open in Gallery" (writes open_intent.json and relies on your shell to switch)
        self.open_gallery_btn = QToolButton()
        self.open_gallery_btn.setText("Open in Gallery")
        self.open_gallery_btn.clicked.connect(self._open_in_gallery)
        controls.addWidget(self.open_gallery_btn)

        self.layout.addLayout(controls)

        # Status / hint
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignLeft)
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    # ---------- Media (Camera) ----------

    def _init_media(self):
        """Initialize device list and connect change signals."""
        try:
            self._refresh_devices()
            QMediaDevices.videoInputsChanged.connect(self._on_video_inputs_changed)
        except Exception as e:
            log.error(f"Error initializing media: {e}")
            self._set_status("Camera unavailable")

    def _refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()

        devices = QMediaDevices.videoInputs()
        for dev in devices:
            name = dev.description() or "Camera"
            self.device_combo.addItem(name, dev)
        self.device_combo.blockSignals(False)

        if devices:
            # pick default
            default_dev = QMediaDevices.defaultVideoInput()
            idx = max(0, next((i for i in range(len(devices)) if devices[i].id() == default_dev.id()), 0))
            self.device_combo.setCurrentIndex(idx)
            self.device_combo.currentIndexChanged.connect(self._on_device_selected)
        else:
            self._set_status("No camera devices found")

    def _start_camera_if_available(self):
        devices = QMediaDevices.videoInputs()
        if not devices:
            return
        dev = self.device_combo.currentData()
        if isinstance(dev, QCameraDevice):
            self._setup_camera(dev)

    def _setup_camera(self, device: QCameraDevice):
        self._starting_up = True
        self._set_status(f"Starting camera: {device.description() or 'Camera'}")

        # Cleanup any old session
        self._teardown_camera()

        try:
            self._camera = QCamera(device)
            self._capture_session = QMediaCaptureSession()
            self._capture_session.setCamera(self._camera)

            # Still image capture (create, then attach to session)
            self._image_capture = QImageCapture()
            try:
                self._image_capture.setFileFormat(QImageCapture.FileFormat.Jpeg)
            except Exception:
                pass

            self._capture_session.setImageCapture(self._image_capture)

            # Video preview target (order doesn’t strictly matter, but this is clear)
            self._capture_session.setVideoOutput(self.video_widget)
            
            # Signals
            self._image_capture.imageCaptured.connect(self._on_image_captured)
            self._image_capture.imageSaved.connect(self._on_image_saved)
            self._image_capture.errorOccurred.connect(self._on_capture_error)
            self._camera.errorChanged.connect(self._on_camera_error)

            # Start
            self._camera.start()
            self._set_status("Camera started")
        except Exception as e:
            log.error(f"Failed to setup camera: {e}")
            self._set_status("Failed to start camera")
        finally:
            self._starting_up = False

    def _teardown_camera(self):
        if self._image_capture:
            try:
                self._image_capture.imageCaptured.disconnect(self._on_image_captured)
            except Exception:
                pass
            try:
                self._image_capture.imageSaved.disconnect(self._on_image_saved)
            except Exception:
                pass
            try:
                self._image_capture.errorOccurred.disconnect(self._on_capture_error)
            except Exception:
                pass

        if self._camera:
            try:
                self._camera.stop()
            except Exception:
                pass

        self._image_capture = None
        self._capture_session = None
        self._camera = None

    # ---------- Events / Signals ----------

    def eventFilter(self, obj, event):
        # Keep it symmetrical with your Gallery App; adjust preview on resize if needed
        if obj is self.container and event.type() == QEvent.Resize:
            # QVideoWidget handles aspect ratio on its own; nothing mandatory here.
            pass
        return False

    def _on_video_inputs_changed(self):
        log.debug("Video inputs changed")
        current_id = None
        if self._camera and self._camera.cameraDevice().isNull() is False:
            current_id = self._camera.cameraDevice().id()
        self._refresh_devices()

        # Try to reselect the previous camera if still present
        if current_id:
            for i in range(self.device_combo.count()):
                dev = self.device_combo.itemData(i)
                if isinstance(dev, QCameraDevice) and dev.id() == current_id:
                    self.device_combo.setCurrentIndex(i)
                    break

        self._start_camera_if_available()

    def _on_device_selected(self, index: int):
        dev = self.device_combo.itemData(index)
        if isinstance(dev, QCameraDevice):
            self._setup_camera(dev)

    def _on_capture_clicked(self):
        if not self._camera or not self._image_capture:
            self._set_status("Camera not ready")
            return

        self._ensure_dcim()
        filepath = self._next_filename()

        # Request capture to file
        try:
            # In Qt6, captureToFile returns an int id; save path via imageSaved signal
            self._image_capture.captureToFile(str(filepath))
            self._set_status(f"Capturing… {filepath.name}")
            self.capture_btn.setEnabled(False)
        except Exception as e:
            log.error(f"Capture failed: {e}")
            self._set_status("Capture failed")

    def _on_image_captured(self, id_: int, preview):
        # Called when an image has been captured but not necessarily saved
        pass  # You can show a soft “flash” effect here if desired

    def _on_image_saved(self, id_: int, file_path: str):
        self.capture_btn.setEnabled(True)
        self._last_saved = Path(file_path)

        # Build standard EXIF values
        operator = os.getenv("USER", "unknown")

        self._attach_standard_exif(
            self._last_saved,
            software="PySide6 Camera App",
        )

        self._set_status(f"Saved: {self._last_saved.name} (EXIF updated)")

    def _on_capture_error(self, id_: int, error, error_string: str):
        self.capture_btn.setEnabled(True)
        msg = error_string or "Capture error"
        self._set_status(msg)
        log.error(f"Capture error [{id_}]: {msg}")

    def _on_camera_error(self):
        if not self._camera:
            return
        err = self._camera.error()
        if err != QCamera.NoError:
            msg = self._camera.errorString() or "Camera error"
            self._set_status(msg)
            log.error(f"Camera error: {msg}")

    # ---------- Helpers ----------

    def _ensure_dcim(self):
        try:
            self._dcim_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.warning(f"Could not create DCIM directory: {e}")

    def _next_filename(self) -> Path:
        """Generate IMG_YYYYMMDD_HHMMSS[_n].jpg in DCIM."""
        now = datetime.now()
        base = f"IMG_{now.strftime('%Y%m%d_%H%M%S')}"
        ext = ".jpg"
        p = self._dcim_dir / f"{base}{ext}"
        n = 1
        while p.exists():
            p = self._dcim_dir / f"{base}_{n}{ext}"
            n += 1
        return p

    def _open_in_gallery(self):
        """Write open_intent.json so your Gallery app will open the last saved photo."""
        if not self._last_saved or not self._last_saved.exists():
            self._set_status("No recent photo to open")
            return

        try:
            # Match the path your Gallery App checks
            intent_path = Path(__file__).resolve().parents[2] / "userdata" / "Data" / "Application" / "gallery" / "open_intent.json"
            intent_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"path": str(self._last_saved)}
            intent_path.write_text(json.dumps(payload), encoding="utf-8")
            self._set_status("Open intent written for Gallery")

            # If your environment supports switching apps programmatically, do it here.
            # Otherwise, user can open the Gallery and it will consume the intent.
        except Exception as e:
            log.error(f"Failed to write open intent: {e}")
            self._set_status("Failed to write open intent")

    def _set_status(self, text: str):
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
        log.debug(text)

    # Optional: clean up explicitly if your host lifecycle requires it
    def __del__(self):
        try:
            self._teardown_camera()
        except Exception:
            pass