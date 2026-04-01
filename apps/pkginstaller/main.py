from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from fs_layout import get_user_data_layout
from logger import get_logger

log = get_logger("pkginstaller")


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container
        self._package_path: Path | None = None
        self._pending_info: dict[str, str] | None = None

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)
        container.setLayout(self._layout)

        self._title = QLabel("Package Installer")
        self._status = QLabel("")
        self._details = QLabel("")
        self._details.setWordWrap(True)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._status)
        self._layout.addWidget(self._details, 1)

        self._actions = QHBoxLayout()
        self._layout.addLayout(self._actions)

        self._render_loading_state()

        self._package_path = self._consume_open_intent()
        if self._package_path is None:
            self._render_error_state("No package was provided.")
            return

        try:
            self._pending_info = self._inspect_pkg(self._package_path)
        except Exception as exc:
            log.exception("Failed to inspect package")
            self._render_error_state(f"Package is invalid: {exc}")
            return

        self._render_confirm_state(self._pending_info)

    def _set_actions(self, actions: list[tuple[str, object]]) -> None:
        while self._actions.count():
            item = self._actions.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            self._actions.addWidget(button)

    def _render_loading_state(self) -> None:
        self._status.setText("Preparing installer...")
        self._details.setText("Loading package information.")
        self._set_actions([])

    def _render_confirm_state(self, info: dict[str, str]) -> None:
        self._status.setText("Do you want to install this application?")
        self._details.setText(
            "\n".join(
                [
                    f"Package: {self._package_path}",
                    f"App ID: {info['app_id']}",
                    f"Name: {info['display_name']}",
                    f"Version: {info['version']}",
                    f"Build: {info['build']}",
                    f"Action: {'Replace existing app' if info['replace'] == 'yes' else 'Install new app'}",
                ]
            )
        )
        self._set_actions(
            [
                ("Cancel", self._close_installer),
                ("Install", self._on_confirm_install),
            ]
        )

    def _render_error_state(self, message: str) -> None:
        self._status.setText("Install failed")
        self._details.setText(message)
        self._set_actions([
            ("Close", self._close_installer),
        ])

    def _render_success_state(self, app_id: str) -> None:
        self._status.setText("Application installed")
        self._details.setText(f"'{app_id}' was installed successfully.")
        self._set_actions(
            [
                ("Done", self._close_installer),
                ("Open", lambda: self._open_installed_app(app_id)),
            ]
        )

    def _on_confirm_install(self) -> None:
        if self._package_path is None:
            self._render_error_state("No package was provided.")
            return

        self._status.setText("Installing application...")
        self._details.setText("Please wait.")
        self._set_actions([])

        try:
            installed_app_id = self._install_pkg(self._package_path)

            if installed_app_id is not None:
                self._refresh_app_registry()
                self._render_success_state(installed_app_id)
            else:
                self._render_error_state("Could not install package.")

        except Exception as exc:
            log.exception("Package installation failed")
            self._render_error_state(f"Install failed: {exc}")

    def _close_installer(self) -> None:
        launch = getattr(self.window, "launch_app", None)
        if callable(launch):
            launch("home")

    def _open_installed_app(self, app_id: str) -> None:
        launch = getattr(self.window, "launch_app", None)
        if callable(launch):
            launch(app_id)

    def _consume_open_intent(self) -> Path | None:
        try:
            intent_path = (
                Path(__file__).resolve().parents[2]
                / "userdata"
                / "Data"
                / "Application"
                / "pkginstaller"
                / "open_intent.json"
            )

            if not intent_path.exists():
                return None

            data = json.loads(intent_path.read_text(encoding="utf-8"))
            raw_path = data.get("path")
        except Exception:
            return None
        finally:
            try:
                intent_path.unlink()
            except Exception:
                pass

        if not raw_path:
            return None

        pkg_path = Path(str(raw_path)).expanduser().resolve()
        if not pkg_path.exists() or not pkg_path.is_file():
            return None

        return pkg_path

    def _inspect_pkg(self, package_path: Path) -> dict[str, str]:
        base_dir = Path(__file__).resolve().parents[2]
        layout = get_user_data_layout(base_dir)

        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if not members:
                raise ValueError("Package is empty")

            for member in members:
                normalized = member.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in Path(normalized).parts:
                    raise ValueError("Package contains unsafe paths")

            with tempfile.TemporaryDirectory(prefix="deletescape_pkginspect_") as tmp_dir:
                extract_root = Path(tmp_dir)
                archive.extractall(extract_root)
                app_root = self._locate_app_root(extract_root)
                manifest_path = app_root / "manifest.json"
                if not manifest_path.exists():
                    raise ValueError("Package is missing manifest.json")

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                app_id_raw = (
                    manifest.get("appId")
                    or manifest.get("app_id")
                    or manifest.get("id")
                )
                app_id = str(app_id_raw).strip() if app_id_raw is not None else ""
                if not app_id:
                    raise ValueError("Manifest missing appId")

                display_name_raw = manifest.get("displayName") or manifest.get("display_name") or app_id
                display_name = str(display_name_raw).strip() if display_name_raw is not None else app_id
                version_raw = manifest.get("version")
                build_raw = manifest.get("build")

                return {
                    "app_id": app_id,
                    "display_name": display_name or app_id,
                    "version": str(version_raw) if version_raw is not None else "unknown",
                    "build": str(build_raw) if build_raw is not None else "unknown",
                    "replace": "yes" if (layout.applications / app_id).exists() else "no",
                }

    def _install_pkg(self, package_path: Path) -> str | None:
        if package_path.suffix.lower() != ".pkg":
            raise ValueError("Only .pkg files are supported")

        base_dir = Path(__file__).resolve().parents[2]
        layout = get_user_data_layout(base_dir)
        layout.ensure_directories()

        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if not members:
                raise ValueError("Package is empty")

            for member in members:
                normalized = member.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in Path(normalized).parts:
                    raise ValueError("Package contains unsafe paths")

            with tempfile.TemporaryDirectory(prefix="deletescape_pkginstall_") as tmp_dir:
                extract_root = Path(tmp_dir)
                archive.extractall(extract_root)

                app_root = self._locate_app_root(extract_root)
                manifest_path = app_root / "manifest.json"
                main_path = app_root / "main.py"
                assets_dir = app_root / "Assets"

                if not manifest_path.exists():
                    raise ValueError("Package is missing manifest.json")
                if not main_path.exists():
                    raise ValueError("Package is missing main.py")
                if not assets_dir.exists() or not assets_dir.is_dir():
                    raise ValueError("Package is missing Assets directory")

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                app_id_raw = (
                    manifest.get("appId")
                    or manifest.get("app_id")
                    or manifest.get("id")
                )
                app_id = str(app_id_raw).strip() if app_id_raw is not None else ""
                if not app_id:
                    raise ValueError("Manifest missing appId")

                destination = layout.applications / app_id
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(app_root, destination)
                return app_id

    def _locate_app_root(self, extracted_root: Path) -> Path:
        manifest_here = extracted_root / "manifest.json"
        main_here = extracted_root / "main.py"

        if manifest_here.exists() and main_here.exists():
            return extracted_root

        child_dirs = [p for p in extracted_root.iterdir() if p.is_dir()]
        if len(child_dirs) == 1:
            child = child_dirs[0]
            if (child / "manifest.json").exists() and (child / "main.py").exists():
                return child

        raise ValueError("Could not locate app root in package")

    def _refresh_app_registry(self) -> None:
        try:
            loader = getattr(self.window, "load_apps", None)
            if callable(loader):
                self.window.apps = loader()
        except Exception:
            log.exception("Failed to refresh app registry after install")
