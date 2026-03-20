from __future__ import annotations

import ast
import json
import sys
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logger import get_logger
from file_handlers import register_handler


log = get_logger("app_registry")


@dataclass
class AppDescriptor:
    app_id: str
    folder: Path
    main_py: Path
    display_name: str
    bundle_id: str | None
    build: int | None
    version: str | None
    permissions: list[str]
    icon_path: Path | None
    hidden: bool
    autostart: bool
    module_name: str
    sys_path_entry: str
    app_class: type | None = None


def _safe_module_name(app_id: str) -> str:
    safe_id = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(app_id))
    return f"deletescape_app_{safe_id}"


def _has_app_class(main_py: Path) -> bool:
    """Cheap validation that an app defines `class App` without importing it."""

    try:
        tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
    except Exception:
        return False

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef) and node.name == "App":
            return True
    return False


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        try:
            return int(value.strip())
        except Exception:
            return None
    return None


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        log.exception("Failed to parse manifest", extra={"manifest": str(manifest_path)})
    return {}


def _normalize_app_id(folder_name: str, manifest: dict[str, Any]) -> str:
    raw = manifest.get("bundleId")
    raw = _coerce_str(raw)

    if raw and raw.strip():
        return raw.strip()

    log.warning("Missing or invalid bundle_id in manifest. A bundle ID will be required in a future release.", folder_name)
    return folder_name

def load_app_class(descriptor: AppDescriptor) -> type | None:
    """Import (or re-import) an app's `main.py` and return its `App` class.

    This is intentionally lazy: apps are only imported when first launched.
    """

    # Ensure local imports inside the app work as if running from its folder.
    try:
        if descriptor.sys_path_entry and descriptor.sys_path_entry not in sys.path:
            sys.path.insert(0, descriptor.sys_path_entry)
    except Exception:
        pass

    spec = importlib.util.spec_from_file_location(descriptor.module_name, str(descriptor.main_py))
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    # Cache so subsequent imports resolve to the same module.
    sys.modules[descriptor.module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        log.exception(
            "Failed to import app module",
            extra={"app_id": descriptor.app_id, "main_py": str(descriptor.main_py), "folder": str(descriptor.folder)},
        )
        return None

    app_cls = getattr(module, "App", None)
    if isinstance(app_cls, type):
        return app_cls
    return None


def unload_app_modules(descriptor: AppDescriptor) -> int:
    """Best-effort unload of modules that were imported from this app's folder.

    Returns the count of removed `sys.modules` entries.
    """

    removed = 0
    app_root: Path
    try:
        app_root = descriptor.folder.resolve()
    except Exception:
        app_root = descriptor.folder

    to_delete: list[str] = []
    for name, mod in list(sys.modules.items()):
        if not name or mod is None:
            continue

        # Always allow removing the main app module by name.
        if name == descriptor.module_name:
            to_delete.append(name)
            continue

        file_path = getattr(mod, "__file__", None)
        origin_path = None
        try:
            spec = getattr(mod, "__spec__", None)
            origin_path = getattr(spec, "origin", None)
        except Exception:
            origin_path = None

        candidate = file_path or origin_path
        if not candidate:
            continue

        try:
            p = Path(candidate).resolve()
            if p.is_relative_to(app_root):
                to_delete.append(name)
        except Exception:
            continue

    for name in to_delete:
        try:
            del sys.modules[name]
            removed += 1
        except Exception:
            pass

    # Remove the sys.path entry for this app so future imports don't accidentally
    # resolve to stale modules after unloading.
    try:
        if descriptor.sys_path_entry in sys.path:
            sys.path.remove(descriptor.sys_path_entry)
    except Exception:
        pass

    try:
        descriptor.app_class = None
    except Exception:
        pass

    return removed


def discover_apps(apps_root: Path) -> dict[str, AppDescriptor]:
    result: dict[str, AppDescriptor] = {}

    if not apps_root.exists() or not apps_root.is_dir():
        log.warning("Apps root missing or not a directory", extra={"apps_root": str(apps_root)})
        return result

    log.debug("Discovering apps", extra={"apps_root": str(apps_root)})

    for entry in sorted(apps_root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue

        main_py = entry / "main.py"
        manifest_path = entry / "manifest.json"
        assets_dir = entry / "Assets"

        if not main_py.exists() or not manifest_path.exists() or not assets_dir.exists():
            log.debug(
                "Skipping folder (missing required files)",
                extra={
                    "folder": str(entry),
                    "has_main": main_py.exists(),
                    "has_manifest": manifest_path.exists(),
                    "has_assets": assets_dir.exists(),
                },
            )
            continue

        manifest = _load_manifest(manifest_path)
        app_id = _normalize_app_id(entry.name, manifest)

        log.debug(
            "Found app candidate",
            extra={"app_id": app_id, "folder": str(entry), "manifest": str(manifest_path)},
        )

        display_name = (
            _coerce_str(manifest.get("displayName"))
            or _coerce_str(manifest.get("display_name"))
            or app_id
        )

        bundle_id = _coerce_str(manifest.get("bundleId") or manifest.get("bundle_id"))
        build = _coerce_int(manifest.get("build"))
        version = _coerce_str(manifest.get("version"))

        permissions_raw = manifest.get("permissions")
        permissions: list[str] = []
        if isinstance(permissions_raw, list):
            permissions = [str(p) for p in permissions_raw if p is not None]

        icon_rel = _coerce_str(manifest.get("icon"))
        icon_path = (entry / icon_rel) if icon_rel else None
        if icon_path is not None and not icon_path.exists():
            icon_path = None

        hidden = bool(manifest.get("hidden", False)) or (app_id == "home")

        autostart = bool(manifest.get("autostart", False)) or bool(manifest.get("autoStart", False))

        if not _has_app_class(main_py):
            log.warning(
                "Skipping app (no App class)",
                extra={"app_id": app_id, "main_py": str(main_py)},
            )
            continue

        module_name = _safe_module_name(app_id)
        sys_path_entry = str(entry)

        result[app_id] = AppDescriptor(
            app_id=app_id,
            folder=entry,
            main_py=main_py,
            display_name=display_name,
            bundle_id=bundle_id,
            build=build,
            version=version,
            permissions=permissions,
            icon_path=icon_path,
            hidden=hidden,
            autostart=autostart,
            module_name=module_name,
            sys_path_entry=sys_path_entry,
            app_class=None,
        )

        # If the manifest declares file handlers, register them system-wide now.
        try:
            fh = manifest.get("file_handlers")
            if isinstance(fh, list) and fh:
                register_handler(app_id, display_name or app_id, extensions=[str(x).lower() for x in fh if x])
        except Exception:
            pass

        log.info(
            "Discovered app",
            extra={
                "app_id": app_id,
                "display_name": display_name,
                "hidden": hidden,
                "autostart": autostart,
                "permissions": permissions,
            },
        )

    log.debug("App discovery complete", extra={"count": len(result)})
    return result
