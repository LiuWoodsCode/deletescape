from __future__ import annotations

import argparse
import getpass
import json
import re
import shutil
import socket
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================
# NINJA‑STYLE BUILD PROGRESS
# ============================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

class BuildProgress:
    def __init__(self, total_steps: int) -> None:
        self.total_steps = total_steps
        self.current_step = 0

    def step(self, name: str) -> None:
        self.current_step += 1
        print(f"\n[{self.current_step}/{self.total_steps}] {name}")

    def file(self, index: int, total: int, message: str) -> None:
        line = f"[{self.current_step}/{self.total_steps}] [{index}/{total}] {message}"

        # Move to start of line
        sys.stdout.write("\r")

        # Clear the entire line (ANSI escape code)
        sys.stdout.write("\x1b[2K")

        # Write new content
        sys.stdout.write(line)

        sys.stdout.flush()

        if index == total:
            print()
# ============================================================
# PATH HELPERS
# ============================================================

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _device_trees_root() -> Path:
    return Path(__file__).resolve().parent / "device-trees"


def _pretty_path(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except Exception:
        return path

# ============================================================
# DEVICE TREE
# ============================================================

def _discover_device_tree_options(device_trees_root: Path) -> list[Path]:
    if not device_trees_root.exists():
        return []

    options: list[Path] = []
    for item in sorted(device_trees_root.iterdir(), key=lambda e: e.name.lower()):
        if item.is_dir() or item.suffix.lower() == ".json":
            options.append(item)
    return options


def _prompt_device_tree_selection(options: list[Path]) -> Path:
    print("Available device trees:")
    for idx, option in enumerate(options, start=1):
        kind = "dir" if option.is_dir() else "json"
        print(f"  [{idx}] {option.name} ({kind})")

    while True:
        raw = input("Select device tree number: ").strip()
        if raw.isdigit():
            selection = int(raw)
            if 1 <= selection <= len(options):
                return options[selection - 1]
        print("Invalid selection.")


def _resolve_device_tree_path(device_tree_arg: str | None, root: Path) -> Path:
    if device_tree_arg:
        user = Path(device_tree_arg)
        candidates = [
            user,
            Path.cwd() / user,
            _repo_root() / user,
            root / device_tree_arg,
        ]
        for c in candidates:
            if c.resolve().exists():
                return c.resolve()
        raise FileNotFoundError(f"Device tree '{device_tree_arg}' not found")

    opts = _discover_device_tree_options(root)
    if not opts:
        raise FileNotFoundError("No device trees found.")
    return _prompt_device_tree_selection(opts)


def _load_device_tree_data(device_tree_path: Path) -> dict[str, Any]:
    if device_tree_path.is_file():
        return json.loads(device_tree_path.read_text(encoding="utf-8"))

    cfg = device_tree_path / "deviceconfig.json"
    if not cfg.exists():
        raise FileNotFoundError(f"{device_tree_path} missing deviceconfig.json")

    return json.loads(cfg.read_text(encoding="utf-8"))

# ============================================================
# FILE CLEANING
# ============================================================

def _delete_directory_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _clear_directory_contents(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def _remove_pycache_and_pyc(root: Path) -> None:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache)
    for ext in ("*.pyc", "*.pyo"):
        for f in root.rglob(ext):
            f.unlink()

# ============================================================
# SYNTAX CHECK (NOW WITH NINJA OUTPUT)
# ============================================================

def _fail_on_python_syntax_errors(root: Path, progress: BuildProgress) -> None:
    py_files = [p for p in root.rglob("*.py") if p.is_file()]
    total = len(py_files)

    failures: list[tuple[Path, Exception]] = []

    for idx, py_file in enumerate(py_files, start=1):
        try:
            source = py_file.read_text(encoding="utf-8")
            rel = _pretty_path(py_file, root)
            compile(source, str(py_file), "exec")
            progress.file(idx, total, f"{rel} has no errors")
        except Exception as exc:
            progress.file(idx, total, f"{rel} errored out!!!")
            failures.append((py_file, exc))

    if failures:
        print("\nSyntax errors detected:\n")
        for path, err in failures:
            print(f"FAILED: {path}\n{err}\n{'-'*60}")
        raise RuntimeError(
            f"Python syntax check failed for {len(failures)} file(s)."
        )

# ============================================================
# BUILD OPS
# ============================================================

def _copy_root_to_stage(src: Path, dst: Path, out_zip: Path) -> None:
    name = out_zip.name.lower()
    def ignore(d, names):
        if Path(d).resolve() == src.resolve():
            return {n for n in names if n.lower() == name}
        return set()
    shutil.copytree(src, dst, ignore=ignore)


def _copy_defaults_to_root(root: Path) -> None:
    defaults = root / "defaults"
    if not defaults.exists():
        raise FileNotFoundError("defaults missing")
    for item in defaults.iterdir():
        dst = root / item.name
        shutil.copytree(item, dst, dirs_exist_ok=True) if item.is_dir() else shutil.copy2(item, dst)


def _slugify(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", v.lower()).strip("-") or "unknown"


def _increment_build_number(p: Path) -> int:
    cur = int(p.read_text().strip()) if p.exists() else 0
    nxt = cur + 1
    p.write_text(f"{nxt}\n")
    return nxt


def _assemble_build_id(osconfig: dict[str, Any], num: int, dt: datetime) -> str:
    return f"deletescape_dev_{num:05d}_{dt.astimezone().strftime('%Y%m%d%H%M%S')}"


def _update_osconfig(root: Path, num: int) -> None:
    path = root / "osconfig.json"
    osconfig = json.loads(path.read_text())
    dt = datetime.now().astimezone()

    osconfig.update({
        "builder_username": getpass.getuser(),
        "builder_hostname": socket.gethostname(),
        "build_datetime": dt.isoformat(timespec="seconds"),
        "build_number": num,
        "build_id": _assemble_build_id(osconfig, num, dt)
    })

    path.write_text(json.dumps(osconfig, indent=2) + "\n")


def _write_deviceconfig(root: Path, data: dict[str, Any]) -> None:
    (root / "deviceconfig.json").write_text(json.dumps(data, indent=2) + "\n")


def _zip_directory(d: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(d))

# ============================================================
# MAIN BUILD
# ============================================================

def build_rootfs(source_root: Path, device_tree_path: Path, output_zip: Path) -> None:

    device_tree_data = _load_device_tree_data(device_tree_path)
    build_number = _increment_build_number(source_root / ".buildnum")

    progress = BuildProgress(total_steps=7)

    with tempfile.TemporaryDirectory(prefix="deletescape_rootfs_") as tmp:
        staged_root = Path(tmp) / "deletescapeos"

        progress.step("Copying source to staging")
        _copy_root_to_stage(source_root, staged_root, output_zip)

        progress.step("Python syntax check")
        _fail_on_python_syntax_errors(staged_root, progress)

        progress.step("Cleaning staged filesystem")
        _delete_directory_if_exists(staged_root / "logs")
        _clear_directory_contents(staged_root / "userdata")
        _remove_pycache_and_pyc(staged_root)

        progress.step("Copying defaults")
        _copy_defaults_to_root(staged_root)

        progress.step("Updating osconfig")
        _update_osconfig(staged_root, build_number)

        progress.step("Writing deviceconfig")
        _write_deviceconfig(staged_root, device_tree_data)

        progress.step("Creating rootfs zip")
        _zip_directory(staged_root, output_zip)

# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-tree")
    parser.add_argument("--source-root", default=str(_repo_root()))
    parser.add_argument("--output", default=str(_repo_root() / "output.zip"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        device_tree = _resolve_device_tree_path(
            args.device_tree, _device_trees_root()
        )
        build_rootfs(
            Path(args.source_root),
            device_tree,
            Path(args.output),
        )
    except Exception as exc:
        print(f"\nBuild failed: {exc}")
        return 1

    print("\n\033[92mBuild completed successfully.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())