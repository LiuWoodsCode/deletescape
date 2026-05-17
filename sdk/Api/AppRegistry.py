from __future__ import annotations

from pathlib import Path

from app_registry import AppDescriptor, discover_apps, load_app_class, unload_app_modules

from ._runtime import bind_window


def discover(apps_root: str | Path) -> dict[str, AppDescriptor]:
    return discover_apps(Path(apps_root))


__all__ = [
    "AppDescriptor",
    "bind_window",
    "discover",
    "discover_apps",
    "load_app_class",
    "unload_app_modules",
]
