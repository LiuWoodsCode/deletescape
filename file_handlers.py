from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict
from logger import PROCESS_START, get_logger
log = get_logger("filehandlers")

_HANDLERS: Dict[str, dict] = {}


def register_handler(app_id: str, display_name: str, *, extensions: List[str] | None = None) -> None:
    _HANDLERS[app_id] = {"app_id": app_id, "display_name": display_name, "extensions": [e.lower() for e in (extensions or [])]}


def unregister_handler(app_id: str) -> None:
    _HANDLERS.pop(app_id, None)


def get_handlers_for_path(path: Path) -> List[dict]:
    ext = (path.suffix or "").lower()
    matches: List[dict] = []
    for h in _HANDLERS.values():
        if not h.get("extensions"):
            continue
        if ext in h.get("extensions", []):
            matches.append(h)
    return matches


def open_with_app(window, app_id: str, path: Path) -> None:
    """Write a simple open intent for the target app and launch it.

    This is a lightweight convention: the app may read
    `./userdata/Data/Application/<app_id>/open_intent.json` on startup.
    """
    try:
        base = Path(__file__).resolve().parent
        intent_dir = base / "userdata" / "Data" / "Application" / app_id
        intent_dir.mkdir(parents=True, exist_ok=True)
        intent_path = intent_dir / "open_intent.json"
        intent_path.write_text(json.dumps({"path": str(path)}), encoding="utf-8")
    except Exception:
        pass

    try:
        launcher = getattr(window, "launch_app", None)
        if callable(launcher):
            launcher(app_id)
    except Exception:
        pass
