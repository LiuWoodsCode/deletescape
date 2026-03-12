import datetime
import importlib
import os
import sys
import platform
import json
from pathlib import Path
import time
import traceback
from PySide6.QtCore import QCoreApplication, Qt, QUrl, QSize, QObject, Signal, Slot, QThread, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtGui import QGuiApplication, QMovie
from home import Deletescape

from app_health import install_exception_hooks

from config import ConfigStore, OSBuildConfigStore
from fs_layout import migrate_legacy_user_data

from logger import configure as configure_logging
from logger import get_logger, install_qt_message_handler

from wallpaper import load_pixmap, scale_crop_center

# this screen is very dumb
# it only works in portrait and can't use a landscape version
# but good thing these images are 1440p
# Recovery mode is meant for a situation where:
# * We can successfully boot the kernel and into Python
# * But we fail booting the deletescape shell
# Currently recovery mode isn't very useful, but it might be possible to use USB networking to allow flashing a new deletescape fs
class RecoveryWindow(QMainWindow):
    def __init__(self, *, image_path: Path, fullscreen=False, fullscreen_screen=None):
        super().__init__()
        self.setWindowTitle("Recovery")
        self.resize(480, 854)
        self._image_path = image_path
        self._fullscreen_requested = bool(fullscreen)
        self._fullscreen_screen = fullscreen_screen
        self._fullscreen_applied = False
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self._label)
        if self._fullscreen_requested and self._fullscreen_screen is not None:
            try:
                self.setGeometry(self._fullscreen_screen.geometry())
            except Exception:
                pass
        self._render()

    def _show_fullscreen_on_screen(self) -> None:
        try:
            if self._fullscreen_screen is not None:
                handle = self.windowHandle()
                if handle is not None:
                    handle.setScreen(self._fullscreen_screen)
                self.showNormal()
                self.setGeometry(self._fullscreen_screen.geometry())
        except Exception:
            pass
        self.showFullScreen()

    def _apply_pending_fullscreen(self) -> None:
        if not self._fullscreen_requested or self._fullscreen_applied:
            return
        self._fullscreen_applied = True
        self._show_fullscreen_on_screen()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fullscreen_requested and not self._fullscreen_applied:
            QTimer.singleShot(0, self._apply_pending_fullscreen)

    def _render(self) -> None:
        pix = load_pixmap(str(self._image_path))
        if pix is None:
            self._label.clear()
            return
        try:
            self._label.setPixmap(scale_crop_center(pix, self._label.size()))
        except Exception:
            self._label.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

def _config_file_is_valid_json_dict(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing JSON file"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"invalid JSON: {e}"
    if not isinstance(data, dict):
        return False, f"expected JSON object, got {type(data).__name__}"
    return True, "ok"

def _boot_bug(code_tuple, *, detail="", subsystem="boot", severity="fatal", **ctx):
    code, num = code_tuple
    return {
        "code": code,
        "numeric": num,
        "severity": severity,
        "subsystem": subsystem,
        "detail": detail,
        "context": ctx,
    }

# Error codes for init check failures
class BootBug:
    RECOVERY_MANUAL            = ("RECOVERY_REQUESTED", 0x0001)
    CFG_MISSING_OR_INVALID     = ("CFG_JSON_INVALID",   0x1002)
    APPS_REGISTRY_MISSING      = ("APPS_REGISTRY_NULL", 0x2001)
    HOME_APP_REQUIRED          = ("HOME_APP_MISSING",   0x2002)
    PYPI_PIEXIF_MISSING        = ("DEP_PIEXIF",         0x3001)
    PYPI_PSUTIL_MISSING        = ("DEP_PSUTIL",         0x3002)
    PYPI_REQUESTS_MISSING      = ("DEP_REQUESTS",       0x3003)
    OK                         = ("OK",                 0x0000)

# run some tests to make sure the OS state is healthy
# if not, send to recovery mode
def _run_boot_init_checks(
    *, 
    base_dir: Path, 
    os_instance: Deletescape, 
    args
) -> tuple[bool, str, dict]:

    config_files = [
        base_dir / "config.json",
        base_dir / "deviceconfig.json",
        base_dir / "osconfig.json",
    ]

    if args.recovery:
        bug = _boot_bug(
            BootBug.RECOVERY_MANUAL,
            subsystem="boot",
            detail="Recovery manually triggered via boot parameter"
        )
        return False, "Manual recovery requested (boot parameter)", bug

    # -------------------------
    # CONFIG VALIDATION
    # -------------------------
    for cfg in config_files:
        ok, detail = _config_file_is_valid_json_dict(cfg)
        if not ok:
            bug = _boot_bug(
                BootBug.CFG_MISSING_OR_INVALID,
                subsystem="config",
                detail=f"{cfg.name}: {detail}",
                file=str(cfg)
            )
            return False, f"Configuration validation failure: {cfg.name}", bug

    # -------------------------
    # APPS REGISTRY
    # -------------------------
    if not hasattr(os_instance, "apps") or not isinstance(getattr(os_instance, "apps"), dict):
        bug = _boot_bug(
            BootBug.APPS_REGISTRY_MISSING,
            subsystem="appreg",
            detail="apps registry missing or non-dict"
        )
        return False, "Application registry unavailable", bug

    if "home" not in os_instance.apps:
        bug = _boot_bug(
            BootBug.HOME_APP_REQUIRED,
            subsystem="appreg",
            detail="Required application 'home' not registered"
        )
        return False, "Required system app missing: home", bug

    # -------------------------
    # PYTHON DEPENDENCIES
    # -------------------------
    if importlib.util.find_spec("piexif") is None:
        bug = _boot_bug(
            BootBug.PYPI_PIEXIF_MISSING,
            subsystem="deps",
            detail="Required dependency piexif not installed"
        )
        return False, "Boot dependency missing: piexif", bug

    if importlib.util.find_spec("psutil") is None:
        bug = _boot_bug(
            BootBug.PYPI_PSUTIL_MISSING,
            subsystem="deps",
            detail="Required dependency psutil not installed"
        )
        return False, "Boot dependency missing: psutil", bug

    if importlib.util.find_spec("requests") is None:
        bug = _boot_bug(
            BootBug.PYPI_REQUESTS_MISSING,
            subsystem="deps",
            detail="Required dependency requests not installed"
        )
        return False, "Boot dependency missing: requests", bug

    return True, "Boot initialization checks passed", _boot_bug(
        BootBug.OK,
        severity="info",
        subsystem="boot"
    )

def _render_splash(label: QLabel, *, image_path: Path) -> bool:
    pix = load_pixmap(str(image_path))
    if pix is None:
        label.clear()
        return False
    try:
        label.setPixmap(scale_crop_center(pix, label.size()))
        return True
    except Exception:
        label.clear()
        return False


def _describe_screen(screen) -> dict:
    geometry = screen.geometry()
    return {
        "screen_name": str(screen.name()),
        "x": int(geometry.x()),
        "y": int(geometry.y()),
        "width": int(geometry.width()),
        "height": int(geometry.height()),
    }


def _resolve_fullscreen_screen(*, display_spec: str | None, log):
    screens = list(QGuiApplication.screens())
    primary = QGuiApplication.primaryScreen()

    if screens:
        log.info("Detected displays", extra={"screens": [_describe_screen(screen) for screen in screens]})
    else:
        log.warning("No Qt displays detected")
        return None

    if not display_spec:
        return primary

    raw_value = str(display_spec).strip()
    if not raw_value:
        return primary

    lowered = raw_value.lower()
    if lowered in {"primary", "default"}:
        return primary

    try:
        index = int(raw_value)
    except ValueError:
        index = None

    if index is not None:
        if 0 <= index < len(screens):
            return screens[index]
        log.warning(
            "Requested fullscreen display index is out of range; falling back to primary",
            extra={"requested_display": raw_value, "available_displays": len(screens)},
        )
        return primary

    exact_matches = [screen for screen in screens if str(screen.name()).strip().lower() == lowered]
    if exact_matches:
        return exact_matches[0]

    partial_matches = [screen for screen in screens if lowered in str(screen.name()).strip().lower()]
    if partial_matches:
        return partial_matches[0]

    log.warning(
        "Requested fullscreen display was not found; falling back to primary",
        extra={"requested_display": raw_value, "available_displays": [_describe_screen(screen) for screen in screens]},
    )
    return primary


import argparse

def main():
    parser = argparse.ArgumentParser(description="Deletescape boot process")

    parser.add_argument("--fullscreen", action="store_true",
                        help="Make the UI fullscreen")
    parser.add_argument("--display", type=str,
                        help="Display index or name to use for fullscreen mode")
    parser.add_argument("--recovery", action="store_true",
                        help="Enter deletescape recovery mode")
    parser.add_argument("--no-webengine-preload", action="store_true",
                        help="Disable preloading QtWebEngine during boot")

    args = parser.parse_args()

    # Configure logging as early as possible so startup issues are captured.
    try:
        build = OSBuildConfigStore(base_dir=Path(__file__).resolve().parent).load()
        default_level = "DEBUG" if str(getattr(build, "channel", "")).lower() == "dev" else "INFO"
    except Exception:
        default_level = "INFO"

    configure_logging(level=default_level)
    install_qt_message_handler()
    log = get_logger("boot")
    base_dir = Path(__file__).resolve().parent

    try:
        result = migrate_legacy_user_data(base_dir)
        log.info("Userdata layout initialized", extra=result)
    except Exception:
        log.exception("Failed to initialize userdata layout")

    # Environment fingerprint (useful for debugging). Kept early so it includes failures during startup.
    try:
        uname = platform.uname()
        log.info(
            "Platform init",
            extra={
                "python": platform.python_version(),
                "python_impl": platform.python_implementation(),
                "python_build": " ".join(platform.python_build()),
                "python_compiler": platform.python_compiler(),
                "executable": sys.executable,
                "cwd": os.getcwd(),
                "argv": list(sys.argv),
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "platform": platform.platform(aliased=True, terse=False),
                "node": platform.node(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "uname": {
                    "system": uname.system,
                    "node": uname.node,
                    "release": uname.release,
                    "version": uname.version,
                    "machine": uname.machine,
                    "processor": uname.processor,
                },
            },
        )
    except Exception:
        log.exception("Failed to log platform init")

    try:
        from PySide6 import QtCore  # type: ignore

        log.info(
            "Qt init",
            extra={
                "qt_version": getattr(QtCore, "QT_VERSION_STR", ""),
                "pyqt_version": getattr(QtCore, "PYQT_VERSION_STR", ""),
            },
        )
    except Exception:
        log.exception("Failed to log Qt init")

    # Must be set BEFORE QApplication is created (used by WebEngine apps).
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    # We use an in-app virtual keyboard instead of the Qt virtual keyboard
    # plugin. Do not set `QT_IM_MODULE` here so Qt won't try to load the
    # system virtual keyboard plugin.

    app = QApplication(sys.argv)
    fullscreen_screen = _resolve_fullscreen_screen(display_spec=args.display, log=log)
    if args.fullscreen and fullscreen_screen is not None:
        log.info("Using fullscreen display", extra=_describe_screen(fullscreen_screen))
    elif args.display:
        log.info("Display selection requested without fullscreen; selection will be ignored", extra={"requested_display": str(args.display)})

    os_instance = Deletescape(
        show_lock_screen_on_start=False,
        full_screen=args.fullscreen,
        fullscreen_screen=fullscreen_screen,
    )
    os_instance.show()

    splash_dir = base_dir / "splash"

    # Splash overlay (boot).
    splash_label = QLabel(os_instance.root)
    splash_label.setGeometry(os_instance.root.rect())
    splash_label.setAlignment(Qt.AlignCenter)
    splash_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    splash_label.setVisible(True)
    splash_label.raise_()

    boot_img = splash_dir / "bootinternal.png"
    _render_splash(splash_label, image_path=boot_img)
    app.processEvents()

    webengine_preload_view = None
    if not getattr(args, "no_webengine_preload", False):
        try:
            log.debug("Now trying to preload webengine. System may appear to hang for a few seconds")
            from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore

            webengine_preload_view = QWebEngineView(os_instance.root)
            webengine_preload_view.setObjectName("BootWebEnginePreloader")
            webengine_preload_view.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            webengine_preload_view.setGeometry(os_instance.root.rect())
            webengine_preload_view.setUrl(QUrl("about:blank"))
            webengine_preload_view.setVisible(True)
            webengine_preload_view.lower()
            log.info("QtWebEngine preload view created under splash screen")
            app.processEvents()
        except Exception:
            log.exception("Failed to preload QtWebEngine during boot")
    else:
        log.info("QtWebEngine preload disabled via boot parameter")

    # Install our custom focus filter to show the in-app virtual keyboard.
    try:
        from input_helper import install_focus_filter  # type: ignore

        # Pass the OS root widget so the keyboard is added into the central
        # content layout (never into QMainWindowLayout directly).
        install_focus_filter(app, host_widget=os_instance.root)
        log.info("Installed custom virtual keyboard focus filter")
    except Exception:
        log.exception("Failed to install custom virtual keyboard focus filter")

    # Run init checks in a background Qt thread so the UI can remain responsive
    # and we can show an animated throbber while the checks run.
    throbber_path = base_dir / "assets" / "icons" / "ui" / "throbber.gif"
    throbber_label = QLabel(os_instance.root)
    throbber_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    throbber_movie = QMovie(str(throbber_path))
    if throbber_movie.isValid():
        # Keep the spinner to a reasonable size rather than its native resolution.
        spinner_size = QSize(48, 48)
        throbber_movie.setScaledSize(spinner_size)
        throbber_label.setMovie(throbber_movie)
        # Position the throbber just below the center of the root widget
        root_rect = os_instance.root.rect()
        w = spinner_size.width()
        h = spinner_size.height()
        x = int((root_rect.width() - w) / 2)
        y = int((root_rect.height() / 2) + 40)
        throbber_label.setGeometry(x, y, w, h)
        throbber_label.setVisible(True)
        throbber_label.raise_()
        throbber_movie.start()
    else:
        throbber_label.clear()

    class BootCheckWorker(QObject):
        finished = Signal(bool, str)

        def __init__(self, base_dir, os_instance, args):
            super().__init__()
            self.base_dir = base_dir
            self.os_instance = os_instance
            self.args = args

        def run(self):
            try:
                ok, reason, details = _run_boot_init_checks(
                    base_dir=self.base_dir,
                    os_instance=self.os_instance,
                    args=self.args
                )

                if not ok:
                    log_dir = Path("./logs")
                    log_dir.mkdir(parents=True, exist_ok=True)

                    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
                    panic_file = log_dir / f"panic_{ts}.json"

                    with panic_file.open("w", encoding="utf-8") as f:
                        json.dump(details, f, indent=2)
            except Exception as e:
                ok, reason = False, f"exception during boot checks: {e}"
            self.finished.emit(ok, reason)

    class BootCheckResultHandler(QObject):
        def __init__(self, *, movie: QMovie, label: QLabel, splash_label: QLabel, preload_view, os_instance: Deletescape, splash_dir: Path, args, log, app: QApplication):
            super().__init__()
            self._movie = movie
            self._throbber_label = label
            self._splash_label = splash_label
            self._preload_view = preload_view
            self._os_instance = os_instance
            self._splash_dir = splash_dir
            self._args = args
            self._log = log
            self._app = app

        def _dispose_preload_view(self) -> None:
            if self._preload_view is None:
                return
            try:
                self._preload_view.hide()
                self._preload_view.deleteLater()
            except Exception:
                self._log.exception("Failed to dispose QtWebEngine preload view")
            finally:
                self._preload_view = None

        @Slot(bool, str)
        def handle(self, ok: bool, reason: str) -> None:
            if self._movie.isValid():
                self._movie.stop()
                self._throbber_label.setVisible(False)
            self._dispose_preload_view()
            if not ok:
                msg = f"init check failure: {reason}"
                self._log.error(msg)
                self._log.info("Device is now in recovery mode.")
                recovery_img = self._splash_dir / "recovery.png"
                try:
                    self._app.setQuitOnLastWindowClosed(False)
                    self._os_instance.hide()
                    self._os_instance.close()
                    self._os_instance.deleteLater()
                except Exception:
                    pass
                self._recovery_window = RecoveryWindow(
                    image_path=recovery_img,
                    fullscreen=self._args.fullscreen,
                    fullscreen_screen=fullscreen_screen,
                )
                self._recovery_window.show()
                self._app.setQuitOnLastWindowClosed(True)
                self._app.processEvents()
                if not recovery_img.exists():
                    self._log.error("Recovery splash missing", extra={"path": str(recovery_img)})
            else:
                self._splash_label.setVisible(False)
                install_exception_hooks(self._os_instance.report_app_crash)
                self._os_instance.show_startup_lock_screen()
                self._app.processEvents()

    # Create worker and thread
    worker_thread = QThread()
    worker = BootCheckWorker(base_dir, os_instance, args)
    worker.moveToThread(worker_thread)
    worker.finished.connect(worker_thread.quit)
    result_handler = BootCheckResultHandler(
        movie=throbber_movie,
        label=throbber_label,
        splash_label=splash_label,
        preload_view=webengine_preload_view,
        os_instance=os_instance,
        splash_dir=splash_dir,
        args=args,
        log=log,
        app=app,
    )
    worker.finished.connect(result_handler.handle)
    worker_thread.started.connect(worker.run)
    worker_thread.start()

    # Enter the Qt main loop; checks will finish asynchronously and trigger callbacks.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()