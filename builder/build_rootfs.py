from __future__ import annotations

import argparse
import getpass
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
import os
import stat

DEBUG = False

# ============================================================
# DEBUG
# ============================================================

def debug(msg: str) -> None:
    if DEBUG:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[DEBUG {ts}] {msg}")

# ============================================================
# NINJA-STYLE BUILD PROGRESS
# ============================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

class BuildProgress:
    def __init__(self, total_steps: int) -> None:
        self.total_steps = total_steps
        self.current_step = 0
        debug(f"BuildProgress initialized with {total_steps} steps")

    def step(self, name: str) -> None:
        self.current_step += 1
        debug(f"Starting step {self.current_step}/{self.total_steps}: {name}")
        print(f"\n[{self.current_step}/{self.total_steps}] {name}")

    def file(self, index: int, total: int, message: str) -> None:
        line = f"[{self.current_step}/{self.total_steps}] [{index}/{total}] {message}"

        sys.stdout.write("\r")
        sys.stdout.write("\x1b[2K")
        sys.stdout.write(line)
        sys.stdout.flush()

        if index == total:
            print()

# ============================================================
# PATH HELPERS
# ============================================================

def _repo_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    debug(f"Repo root resolved to {root}")
    return root

def _handle_remove_readonly(func, path, exc):
    excvalue = exc[1]
    if func in (os.remove, os.rmdir, os.unlink):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise
    
def _device_trees_root() -> Path:
    root = Path(__file__).resolve().parent / "device-trees"
    debug(f"Device trees root resolved to {root}")
    return root

def _pretty_path(path: Path, root: Path) -> Path:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return rel
    except Exception:
        return path

# ============================================================
# DEVICE TREE
# ============================================================

def _discover_device_tree_options(device_trees_root: Path) -> list[Path]:
    debug(f"Scanning for device trees in {device_trees_root}")

    if not device_trees_root.exists():
        debug("Device tree root does not exist")
        return []

    options: list[Path] = []

    for item in sorted(device_trees_root.iterdir(), key=lambda e: e.name.lower()):
        if item.is_dir() or item.suffix.lower() == ".json":
            debug(f"Found device tree candidate: {item}")
            options.append(item)

    debug(f"Total device trees discovered: {len(options)}")
    return options


def _prompt_device_tree_selection(options: list[Path]) -> Path:
    print("Available device trees:")
    for idx, option in enumerate(options, start=1):
        kind = "dir" if option.is_dir() else "json"
        print(f"  [{idx}] {option.name} ({kind})")

    while True:
        raw = input("Select device tree number: ").strip()
        debug(f"User selected raw device tree input: {raw}")

        if raw.isdigit():
            selection = int(raw)
            if 1 <= selection <= len(options):
                chosen = options[selection - 1]
                debug(f"Device tree selected: {chosen}")
                return chosen

        print("Invalid selection.")


def _resolve_device_tree_path(device_tree_arg: str | None, root: Path) -> Path:
    debug(f"Resolving device tree path from argument: {device_tree_arg}")

    if device_tree_arg:
        user = Path(device_tree_arg)

        candidates = [
            user,
            Path.cwd() / user,
            _repo_root() / user,
            root / device_tree_arg,
        ]

        for c in candidates:
            debug(f"Checking candidate path: {c}")
            if c.resolve().exists():
                resolved = c.resolve()
                debug(f"Device tree resolved to {resolved}")
                return resolved

        raise FileNotFoundError(f"Device tree '{device_tree_arg}' not found")

    opts = _discover_device_tree_options(root)

    if not opts:
        raise FileNotFoundError("No device trees found.")

    return _prompt_device_tree_selection(opts)


def _load_device_tree_data(device_tree_path: Path) -> dict[str, Any]:
    debug(f"Loading device tree data from {device_tree_path}")

    if device_tree_path.is_file():
        debug("Device tree is JSON file")
        return json.loads(device_tree_path.read_text(encoding="utf-8"))

    cfg = device_tree_path / "deviceconfig.json"

    if not cfg.exists():
        raise FileNotFoundError(f"{device_tree_path} missing deviceconfig.json")

    debug(f"Reading deviceconfig.json from {cfg}")
    return json.loads(cfg.read_text(encoding="utf-8"))

# ============================================================
# FILE CLEANING
# ============================================================

def _delete_directory_if_exists(path: Path) -> None:
    debug(f"Checking for directory removal: {path}")

    if path.exists():
        debug(f"Deleting directory: {path}")
        shutil.rmtree(path, onerror=_handle_remove_readonly)


def _clear_directory_contents(path: Path) -> None:
    debug(f"Clearing directory contents: {path}")

    path.mkdir(parents=True, exist_ok=True)

    for child in path.iterdir():
        debug(f"Removing child: {child}")

        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _remove_pycache_and_pyc(root: Path) -> None:
    debug("Removing __pycache__ directories")

    for cache in root.rglob("__pycache__"):
        debug(f"Removing cache directory: {cache}")
        shutil.rmtree(cache)

    for ext in ("*.pyc", "*.pyo"):
        for f in root.rglob(ext):
            debug(f"Removing compiled file: {f}")
            f.unlink()

# ============================================================
# SYNTAX CHECK
# ============================================================

def _fail_on_python_syntax_errors(root: Path, progress: BuildProgress) -> None:
    debug("Starting Python syntax validation")

    py_files = [p for p in root.rglob("*.py") if p.is_file()]
    total = len(py_files)

    debug(f"Python files discovered for syntax check: {total}")

    failures: list[tuple[Path, Exception]] = []

    for idx, py_file in enumerate(py_files, start=1):
        rel = _pretty_path(py_file, root)
        debug(f"Checking syntax: {rel}")

        try:
            source = py_file.read_text(encoding="utf-8")
            compile(source, str(py_file), "exec")
            progress.file(idx, total, f"{rel} has no errors")

        except Exception as exc:
            debug(f"Syntax error in {py_file}: {exc}")
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
    debug(f"Copying root filesystem from {src} to staging {dst}")

    name = out_zip.name.lower()

    def ignore(d, names):
        if Path(d).resolve() == src.resolve():
            ignored = {n for n in names if n.lower() == name}
            if ignored:
                debug(f"Ignoring files during copy: {ignored}")
            return ignored
        return set()

    shutil.copytree(src, dst, ignore=ignore)
    debug("Source copied to staging successfully")


def _copy_defaults_to_root(root: Path) -> None:
    defaults = root / "defaults"

    debug(f"Copying defaults from {defaults}")

    if not defaults.exists():
        raise FileNotFoundError("defaults missing")

    for item in defaults.iterdir():
        dst = root / item.name
        debug(f"Copying default item {item} -> {dst}")

        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)


def _increment_build_number(p: Path) -> int:
    debug(f"Incrementing build number at {p}")

    cur = int(p.read_text().strip()) if p.exists() else 0
    nxt = cur + 1

    p.write_text(f"{nxt}\n")

    debug(f"Build number updated: {cur} -> {nxt}")

    return nxt


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _assemble_build_id(osconfig: dict[str, Any], num: int, dt: datetime, branch: str, commit: str) -> str:
    build_id = f"{branch}_{commit}_{num:05d}_{dt.astimezone().strftime('%Y%m%d-%H%M')}"
    debug(f"Generated build ID: {build_id}")
    return build_id


def _update_osconfig(root: Path, num: int) -> None:
    path = root / "osconfig.json"
    debug(f"Updating osconfig at {path}")

    osconfig = json.loads(path.read_text())
    dt = datetime.now().astimezone()

    git_branch = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    git_commit = _git(["git", "rev-parse", "--short", "HEAD"])

    osconfig.update({
        "builder_username": getpass.getuser(),
        "builder_hostname": socket.gethostname(),
        "build_datetime": dt.isoformat(timespec="seconds"),
        "build_number": num,
        "git_branch": git_branch,
        "git_commit": git_commit,
        "builder_hostos": platform.uname(),
        "build_id": _assemble_build_id(osconfig, num, dt, git_branch, git_commit)
    })

    path.write_text(json.dumps(osconfig, indent=2) + "\n")

    debug("osconfig.json updated successfully")


def _write_deviceconfig(root: Path, data: dict[str, Any]) -> None:
    path = root / "deviceconfig.json"
    debug(f"Writing deviceconfig to {path}")
    path.write_text(json.dumps(data, indent=2) + "\n")


def _zip_directory(d: Path, out: Path) -> None:
    debug(f"Creating zip archive {out} from {d}")

    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(d.rglob("*")):
            rel = p.relative_to(d)

            if p.is_dir():
                # Explicitly add empty directories
                if not any(p.iterdir()):
                    debug(f"Adding empty dir to zip: {rel}/")
                    z.writestr(str(rel) + "/", "")
            else:
                debug(f"Adding to zip: {rel}")
                z.write(p, rel)

    debug("Zip archive created successfully")

# ============================================================
# MAIN BUILD
# ============================================================

def build_rootfs(source_root: Path, device_tree_path: Path, output_zip: Path) -> None:

    debug("Starting rootfs build")

    device_tree_data = _load_device_tree_data(device_tree_path)

    build_number = _increment_build_number(source_root / ".buildnum")

    progress = BuildProgress(total_steps=7)

    with tempfile.TemporaryDirectory(prefix="deletescape_rootfs_") as tmp:

        debug(f"Temporary staging directory created: {tmp}")

        staged_root = Path(tmp) / "deletescapeos"

        progress.step("Copying source to staging")
        _copy_root_to_stage(source_root, staged_root, output_zip)

        progress.step("Python syntax check")
        _fail_on_python_syntax_errors(staged_root, progress)

        progress.step("Cleaning staged filesystem")
        _delete_directory_if_exists(staged_root / "logs")
        _delete_directory_if_exists(staged_root / ".git")
        _delete_directory_if_exists(staged_root / ".vscode")
        _delete_directory_if_exists(staged_root / ".github")
        _delete_directory_if_exists(staged_root / "assistant" / "backend")
        _delete_directory_if_exists(staged_root / "docs")
        _delete_directory_if_exists(staged_root / "builder")
        _delete_directory_if_exists(staged_root / "notes")
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

    debug("Build completed successfully")

# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--device-tree")
    parser.add_argument("--source-root", default=str(_repo_root()))
    parser.add_argument("--output", default=str(_repo_root() / "output.zip"))
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    debug(f"CLI args parsed: {args}")

    return args


def main() -> int:
    args = parse_args()

    try:

        device_tree = _resolve_device_tree_path(
            args.device_tree,
            _device_trees_root()
        )

        build_rootfs(
            Path(args.source_root),
            device_tree,
            Path(args.output),
        )

    except Exception as exc:
        print(f"\nBuild failed: {exc}")
        debug(f"Exception details: {repr(exc)}")
        return 1

    print("\n\033[92mBuild completed successfully.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())