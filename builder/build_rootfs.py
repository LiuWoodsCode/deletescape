from __future__ import annotations

import argparse
import getpass
import hashlib
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


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _assemble_build_id(osconfig: dict[str, Any], dt: datetime, branch: str, commit: str) -> str:
    build_id = f"{branch}_{commit}_{dt.astimezone().strftime('%Y%m%d-%H%M')}"
    debug(f"Generated build ID: {build_id}")
    return build_id


def _update_osconfig(root: Path) -> None:
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
        "git_branch": git_branch,
        "git_commit": git_commit,
        "builder_hostos": platform.uname(),
        "build_id": _assemble_build_id(osconfig, dt, git_branch, git_commit)
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


def _collect_component_entries(root: Path, relative_paths: list[Path]) -> list[str]:
    entries: set[str] = set()

    for rel in relative_paths:
        src = root / rel

        if not src.exists():
            debug(f"Skipping missing component path: {rel}")
            continue

        if src.is_file():
            entries.add(rel.as_posix())
            continue

        children = sorted(src.rglob("*"))

        if not children:
            entries.add(rel.as_posix().rstrip("/") + "/")
            continue

        for child in children:
            child_rel = child.relative_to(root).as_posix()

            if child.is_dir() and not any(child.iterdir()):
                entries.add(child_rel.rstrip("/") + "/")
            elif child.is_file():
                entries.add(child_rel)

    return sorted(entries)


def _zip_selected_paths(root: Path, relative_paths: list[Path], out_zip: Path) -> list[str]:
    debug(f"Creating component zip {out_zip} from {len(relative_paths)} path(s)")

    entries = _collect_component_entries(root, relative_paths)

    out_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in entries:
            if entry.endswith("/"):
                debug(f"Adding empty dir to component zip: {entry}")
                z.writestr(entry, "")
            else:
                debug(f"Adding path to component zip: {entry}")
                z.write(root / Path(entry), entry)

    return entries


def _zip_directory_contents(directory: Path, out_zip: Path) -> list[str]:
    debug(f"Creating component zip {out_zip} from directory contents of {directory}")

    entries: list[str] = []

    out_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob("*")):
            rel = path.relative_to(directory).as_posix()

            if path.is_dir():
                if not any(path.iterdir()):
                    entry = rel.rstrip("/") + "/"
                    debug(f"Adding empty dir to component zip: {entry}")
                    z.writestr(entry, "")
                    entries.append(entry)
            else:
                debug(f"Adding path to component zip: {rel}")
                z.write(path, rel)
                entries.append(rel)

    return entries


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _build_ota_zip(staged_root: Path, output_zip: Path) -> None:
    debug("Creating OTA bundle")

    component_zips: dict[str, Path] = {}
    component_layout: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="deletescape_ota_components_") as component_tmp:
        component_dir = Path(component_tmp)

        def add_component(zip_name: str, relative_paths: list[Path]) -> None:
            if not relative_paths:
                debug(f"Skipping empty component list for {zip_name}")
                return

            zip_path = component_dir / zip_name
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            entries = _zip_selected_paths(staged_root, relative_paths, zip_path)

            with zipfile.ZipFile(zip_path, "r") as z:
                if len(z.infolist()) == 0:
                    debug(f"Skipping empty component zip: {zip_name}")
                    return

            component_zips[zip_name] = zip_path
            component_layout[zip_name] = {
                "zip_path": f"components/{zip_name}",
                "install_root": "/",
                "entries": [
                    {
                        "archive_path": entry,
                        "install_path": f"/{entry.rstrip('/')}",
                        "type": "directory" if entry.endswith("/") else "file",
                    }
                    for entry in entries
                ],
            }

        def add_app_component(app_dir: Path) -> None:
            zip_name = f"app/{app_dir.name}.pkg"
            zip_path = component_dir / zip_name
            entries = _zip_directory_contents(app_dir, zip_path)

            with zipfile.ZipFile(zip_path, "r") as z:
                if len(z.infolist()) == 0:
                    debug(f"Skipping empty app component zip: {zip_name}")
                    return

            component_zips[zip_name] = zip_path
            component_layout[zip_name] = {
                "zip_path": f"components/{zip_name}",
                "install_root": f"/apps/{app_dir.name}",
                "entries": [
                    {
                        "archive_path": entry,
                        "install_path": f"/apps/{app_dir.name}/{entry.rstrip('/')}",
                        "type": "directory" if entry.endswith("/") else "file",
                    }
                    for entry in entries
                ],
            }

        apps_dir = staged_root / "apps"
        if apps_dir.exists() and apps_dir.is_dir():
            app_common = [
                Path("apps") / p.name
                for p in apps_dir.iterdir()
                if p.is_file() and p.name != "__pycache__"
            ]
            add_component("apps_common.zip", app_common)

            for app_dir in sorted(apps_dir.iterdir(), key=lambda p: p.name.lower()):
                if app_dir.is_dir() and app_dir.name != "__pycache__":
                    add_app_component(app_dir)

        splash_dir = staged_root / "splash"
        if splash_dir.exists():
            add_component("splash_screens.zip", [Path("splash")])

        kernel_dir = staged_root / "kernel"
        if kernel_dir.exists():
            add_component("sayori_kernel.zip", [Path("kernel")])

        drivers_dir = staged_root / "drivers"
        if drivers_dir.exists() and drivers_dir.is_dir():
            drivers_common = [
                Path("drivers") / p.name
                for p in drivers_dir.iterdir()
                if p.is_file() and p.name != "__pycache__"
            ]
            add_component("drivers_common.zip", drivers_common)

            for driver_component in sorted(drivers_dir.iterdir(), key=lambda p: p.name.lower()):
                if driver_component.is_dir() and driver_component.name != "__pycache__":
                    add_component(
                        f"driver_{driver_component.name}.zip",
                        [Path("drivers") / driver_component.name],
                    )

        icons_dir = staged_root / "assets" / "icons"
        if icons_dir.exists():
            add_component("system_icons.zip", [Path("assets") / "icons"])

        wallpapers_dir = staged_root / "assets" / "wallpaper"
        if wallpapers_dir.exists():
            add_component("wallpapers.zip", [Path("assets") / "wallpaper"])

        inclus_font_dir = staged_root / "assets" / "fonts"
        if inclus_font_dir.exists():
            add_component("fonts.zip", [Path("assets") / "fonts"])
            
        defaults_dir = staged_root / "defaults"
        if defaults_dir.exists():
            add_component("defaults.zip", [Path("defaults")])

        add_component("configs.zip", [Path("osconfig.json"), Path("deviceconfig.json")])

        core_os_entries = [
            Path(item.name)
            for item in staged_root.iterdir()
            if item.is_file() and item.name not in {"deviceconfig.json", "osconfig.json"}
        ]
        add_component("core_os.zip", core_os_entries)

        if not component_zips:
            raise RuntimeError("No OTA components were generated.")

        osconfig_path = staged_root / "osconfig.json"
        deviceconfig_path = staged_root / "deviceconfig.json"

        if not osconfig_path.exists():
            raise FileNotFoundError("staged root missing osconfig.json")

        if not deviceconfig_path.exists():
            raise FileNotFoundError("staged root missing deviceconfig.json")

        osconfig_data = json.loads(osconfig_path.read_text(encoding="utf-8"))
        deviceconfig_data = json.loads(deviceconfig_path.read_text(encoding="utf-8"))

        manifest = {
            "manifest_version": 2,
            "algorithm": "sha256",
            "components": {
                zip_name: _sha256_file(zip_path)
                for zip_name, zip_path in sorted(component_zips.items())
            },
            "osconfig": osconfig_data,
            "deviceconfig": deviceconfig_data,
        }

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as ota:
            for zip_name, zip_path in sorted(component_zips.items()):
                ota.write(zip_path, Path("components") / zip_name)

            ota.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")

    debug("OTA zip created successfully")

# ============================================================
# MAIN BUILD
# ============================================================

def build_rootfs(
    source_root: Path,
    device_tree_path: Path,
    output_zip: Path,
    build_format: str = "rootfs",
) -> None:

    debug("Starting rootfs build")

    device_tree_data = _load_device_tree_data(device_tree_path)

    progress = BuildProgress(total_steps=7)

    with tempfile.TemporaryDirectory(prefix="deletescape_rootfs_") as tmp:

        debug(f"Temporary staging directory created: {tmp}")

        staged_root = Path(tmp) / "deletescapeos"

        progress.step("Copying source to staging")
        _copy_root_to_stage(source_root, staged_root, output_zip)

        progress.step("Cleaning staged filesystem")
        _delete_directory_if_exists(staged_root / "logs")
        _delete_directory_if_exists(staged_root / ".git")
        _delete_directory_if_exists(staged_root / ".vscode")
        _delete_directory_if_exists(staged_root / ".github")
        _delete_directory_if_exists(staged_root / "assistant" / "backend")
        _delete_directory_if_exists(staged_root / "docs")
        _delete_directory_if_exists(staged_root / "builder")
        _delete_directory_if_exists(staged_root / ".venv")
        _delete_directory_if_exists(staged_root / "notes")
        _clear_directory_contents(staged_root / "userdata")
        _remove_pycache_and_pyc(staged_root)

        progress.step("Python syntax check")
        _fail_on_python_syntax_errors(staged_root, progress)

        progress.step("Copying defaults")
        _copy_defaults_to_root(staged_root)

        progress.step("Updating osconfig")
        _update_osconfig(staged_root)

        progress.step("Writing deviceconfig")
        _write_deviceconfig(staged_root, device_tree_data)

        if build_format == "ota":
            progress.step("Creating OTA zip")
            _build_ota_zip(staged_root, output_zip)
        else:
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
    parser.add_argument("--format", choices=["rootfs", "ota"], default="rootfs")
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
            args.format,
        )

    except Exception as exc:
        print(f"\nBuild failed: {exc}")
        debug(f"Exception details: {repr(exc)}")
        return 1

    print("\n\033[92mBuild completed successfully.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())