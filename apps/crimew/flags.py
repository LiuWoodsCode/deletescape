import os
from pathlib import Path
import time
import json
import threading
# -------------------------
# Paths
# -------------------------

_WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = Path.home() / ".tinybrowser_settings.json"
_FLAGS_PATH = os.path.join(_WORKSPACE_DIR, "data", "flags.json")

# -------------------------
# Internal Caches
# -------------------------

_config_lock = threading.Lock()
_config_cache: dict | None = None
_config_mtime: float | None = None

_flags_lock = threading.Lock()
_flags_cache: dict | None = None
_flags_mtime: float | None = None


# -------------------------
# Config Handling
# -------------------------

def _load_config_file() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_config_cached(ttl_seconds: float = 2.0) -> dict:
    global _config_cache, _config_mtime
    now = time.time()

    with _config_lock:
        cached = _config_cache
        cached_at = getattr(get_config_cached, "_cached_at", 0.0)
        if cached is not None and (now - cached_at) < ttl_seconds:
            return dict(cached)

    try:
        mtime = os.path.getmtime(_CONFIG_PATH)
    except Exception:
        mtime = None

    with _config_lock:
        if _config_cache is not None and _config_mtime == mtime:
            return dict(_config_cache)

    data = _load_config_file()

    with _config_lock:
        _config_cache = dict(data)
        _config_mtime = mtime
        setattr(get_config_cached, "_cached_at", now)
        return dict(_config_cache)


def save_config_file(data: dict) -> bool:
    if not isinstance(data, dict):
        return False

    tmp = str(_CONFIG_PATH) + ".tmp"
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(raw)
            f.write("\n")
        os.replace(tmp, str(_CONFIG_PATH))
    except Exception:
        return False

    with _config_lock:
        global _config_cache, _config_mtime
        _config_cache = dict(data)
        try:
            _config_mtime = os.path.getmtime(_CONFIG_PATH)
        except Exception:
            _config_mtime = None
        setattr(get_config_cached, "_cached_at", time.time())

    return True


# -------------------------
# Flags Handling
# -------------------------

def _load_flags_file() -> dict:
    if not os.path.exists(_FLAGS_PATH):
        return {}
    try:
        with open(_FLAGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_flags_cached(ttl_seconds: float = 2.0) -> dict:
    global _flags_cache, _flags_mtime
    now = time.time()

    with _flags_lock:
        cached = _flags_cache
        cached_at = getattr(get_flags_cached, "_cached_at", 0.0)
        if cached is not None and (now - cached_at) < ttl_seconds:
            return dict(cached)

    try:
        mtime = os.path.getmtime(_FLAGS_PATH)
    except Exception:
        mtime = None

    with _flags_lock:
        if _flags_cache is not None and _flags_mtime == mtime:
            return dict(_flags_cache)

    data = _load_flags_file()

    with _flags_lock:
        _flags_cache = dict(data)
        _flags_mtime = mtime
        setattr(get_flags_cached, "_cached_at", now)
        return dict(_flags_cache)


# -------------------------
# Experiment Resolution
# -------------------------

def _normalize_experiments_state(cfg: dict | None) -> dict:
    cfg = cfg if isinstance(cfg, dict) else {}
    raw = cfg.get("experiments")
    raw = raw if isinstance(raw, dict) else {}
    flags = raw.get("flags")
    flags = flags if isinstance(flags, dict) else {}

    out_flags: dict[str, str] = {}
    for k, v in flags.items():
        if isinstance(k, str) and k.strip() and isinstance(v, str):
            out_flags[k.strip()] = v.strip() or "default"

    return {"flags": out_flags}


def get_experiment_choice(flag_id: str) -> str:
    cfg = get_config_cached()
    exp = _normalize_experiments_state(cfg)
    return exp["flags"].get(flag_id, "default")


def get_flag_default_choice(flag_id: str, fallback: str = "disabled") -> str:
    flags_doc = get_flags_cached()
    defs = flags_doc.get("flags") if isinstance(flags_doc, dict) else []

    for f in defs:
        if isinstance(f, dict) and f.get("id") == flag_id:
            d = f.get("default")
            if isinstance(d, str) and d.strip():
                return d.strip()

    return fallback


def resolve_bool_flag(flag_id: str, default_value: bool = False) -> bool:
    choice = get_experiment_choice(flag_id)

    if choice == "enabled":
        return True
    if choice == "disabled":
        return False

    default_choice = get_flag_default_choice(
        flag_id,
        fallback=("enabled" if default_value else "disabled")
    )

    return default_choice == "enabled"


# -------------------------
# Optional Helpers
# -------------------------

def set_experiment_choice(flag_id: str, choice: str) -> bool:
    """Persist a single flag choice into config.json (best-effort)."""
    if not isinstance(flag_id, str) or not isinstance(choice, str):
        return False

    cfg = get_config_cached()
    cfg = dict(cfg)

    exp = cfg.get("experiments")
    exp = dict(exp) if isinstance(exp, dict) else {}
    flags = exp.get("flags")
    flags = dict(flags) if isinstance(flags, dict) else {}

    flags[flag_id.strip()] = choice.strip() or "default"
    exp["flags"] = flags
    cfg["experiments"] = exp

    return save_config_file(cfg)


# -------------------------
# Search Settings
# -------------------------

_SEARCH_PROVIDER_CHOICES = {"google", "bing", "duckduckgo"}


def get_search_provider(default: str = "google") -> str:
    cfg = get_config_cached()
    search = cfg.get("search") if isinstance(cfg, dict) else {}
    search = search if isinstance(search, dict) else {}
    provider = search.get("provider", default)

    if isinstance(provider, str):
        normalized = provider.strip().lower()
        if normalized in _SEARCH_PROVIDER_CHOICES:
            return normalized

    normalized_default = default.strip().lower() if isinstance(default, str) else "google"
    if normalized_default in _SEARCH_PROVIDER_CHOICES:
        return normalized_default
    return "google"


def set_search_provider(provider: str) -> bool:
    if not isinstance(provider, str):
        return False

    normalized = provider.strip().lower()
    if normalized not in _SEARCH_PROVIDER_CHOICES:
        return False

    cfg = get_config_cached()
    cfg = dict(cfg)
    search = cfg.get("search")
    search = dict(search) if isinstance(search, dict) else {}
    search["provider"] = normalized
    cfg["search"] = search

    return save_config_file(cfg)
