from __future__ import annotations

import argparse
import getpass
import json
import re
import shutil
import socket
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _device_trees_root() -> Path:
    return Path(__file__).resolve().parent / "device-trees"


def _discover_device_tree_options(device_trees_root: Path) -> list[Path]:
    if not device_trees_root.exists():
        return []

    options: list[Path] = []
    for item in sorted(device_trees_root.iterdir(), key=lambda entry: entry.name.lower()):
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
        if not raw.isdigit():
            print("Please enter a number.")
            continue

        selection = int(raw)
        if 1 <= selection <= len(options):
            return options[selection - 1]

        print("Selection out of range.")


def _resolve_device_tree_path(device_tree_arg: str | None, device_trees_root: Path) -> Path:
    if device_tree_arg:
        user_path = Path(device_tree_arg)
        candidates = [
            user_path,
            Path.cwd() / user_path,
            _repo_root() / user_path,
            device_trees_root / device_tree_arg,
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved
        raise FileNotFoundError(
            f"Device tree '{device_tree_arg}' was not found as a path or under {device_trees_root}"
        )

    options = _discover_device_tree_options(device_trees_root)
    if not options:
        raise FileNotFoundError(
            f"No device trees found in {device_trees_root}. Provide --device-tree with a path."
        )

    return _prompt_device_tree_selection(options)


def _load_device_tree_data(device_tree_path: Path) -> dict[str, Any]:
    if device_tree_path.is_file() and device_tree_path.suffix.lower() == ".json":
        with device_tree_path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    elif device_tree_path.is_dir():
        device_config_candidate = device_tree_path / "deviceconfig.json"
        if not device_config_candidate.exists():
            raise FileNotFoundError(
                f"Device tree directory {device_tree_path} is missing deviceconfig.json"
            )
        with device_config_candidate.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    else:
        raise ValueError(
            "Device tree must be a directory containing deviceconfig.json or a JSON file"
        )

    if not isinstance(data, dict):
        raise ValueError("Device tree JSON must be an object")
    return data


def _delete_directory_if_exists(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        print(f"Deleted directory {path}")

def _clear_directory_contents(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            print(f"Removed tree of {child}")
        else:
            child.unlink()
            print(f"Unlinked {child}")

def _remove_pycache_and_pyc(root: Path) -> None:
    for cache_dir in root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
            print(f"Removed directory {cache_dir}")

    for pyc in root.rglob("*.pyc"):
        if pyc.is_file():
            print(f"Removing {pyc}")
            pyc.unlink()

    for pyo in root.rglob("*.pyo"):
        if pyo.is_file():
            print(f"Removing {pyo}")
            pyo.unlink()

def _copy_defaults_to_root(staged_root: Path) -> None:
    defaults_dir = staged_root / "defaults"
    if not defaults_dir.exists() or not defaults_dir.is_dir():
        raise FileNotFoundError(f"Missing defaults directory in staged root: {defaults_dir}")

    for item in defaults_dir.iterdir():
        destination = staged_root / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
            print(f"Copied directory {item} to {destination}")
        else:
            shutil.copy2(item, destination)
            print(f"Copied file {item} to {destination}")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _increment_build_number(buildnum_path: Path) -> int:
    current = 0
    if buildnum_path.exists() and buildnum_path.is_file():
        raw = buildnum_path.read_text(encoding="utf-8").strip()
        if raw:
            try:
                current = int(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid .buildnum contents in {buildnum_path}: '{raw}'") from exc

    next_build = current + 1
    print(f"Build number incremented, was {current}, now {next_build}")
    buildnum_path.write_text(f"{next_build}\n", encoding="utf-8")
    return next_build


def _assemble_build_id(osconfig: dict[str, Any], build_number: int, build_dt: datetime) -> str:
    os_name = _slugify(str("deletescape")) # TODO: use a git branch instead???
    os_version = _slugify(str(osconfig.get("os_version", "0")))
    channel = _slugify(str(osconfig.get("channel", "dev")))
    timestamp = build_dt.astimezone().strftime("%Y%m%d%H%M%S")
    print("Assembled build ID")
    return f"{os_name}_{channel}_{build_number:05d}_{timestamp}"


def _update_osconfig(staged_root: Path, build_number: int) -> None:
    osconfig_path = staged_root / "osconfig.json"
    if not osconfig_path.exists():
        raise FileNotFoundError(f"Missing osconfig.json in staged root: {osconfig_path}")

    with osconfig_path.open("r", encoding="utf-8") as stream:
        osconfig = json.load(stream)

    if not isinstance(osconfig, dict):
        raise ValueError("osconfig.json must be a JSON object")

    build_dt = datetime.now().astimezone()
    builder_user = getpass.getuser()
    builder_host = socket.gethostname()
    curtime = build_dt.isoformat(timespec="seconds")
    buid = _assemble_build_id(osconfig, build_number=build_number, build_dt=build_dt)
    osconfig["builder_username"] = builder_user
    osconfig["builder_hostname"] = builder_host
    osconfig["build_datetime"] = curtime
    osconfig["build_number"] = build_number
    osconfig["build_id"] = buid

    print(f"New data saved to osconfig: \nbuild_id: {buid}\nbuild_number: {build_number}\nbuild_datetime: {curtime}\nbuilder_username: {builder_user}\nbuilder_hostname: {builder_host}")
    with osconfig_path.open("w", encoding="utf-8") as stream:
        json.dump(osconfig, stream, indent=2)
        stream.write("\n")


def _write_deviceconfig(staged_root: Path, device_tree_data: dict[str, Any]) -> None:
    deviceconfig_path = staged_root / "deviceconfig.json"
    with deviceconfig_path.open("w", encoding="utf-8") as stream:
        json.dump(device_tree_data, stream, indent=2)
        stream.write("\n")
    print(f"Wrote new device config to {deviceconfig_path}")


def _copy_root_to_stage(source_root: Path, staged_root: Path, output_zip: Path) -> None:
    output_zip_name = output_zip.name.lower()

    def ignore_filter(current_dir: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        if Path(current_dir).resolve() == source_root.resolve():
            for name in names:
                if name.lower() == output_zip_name:
                    ignored.add(name)
        return ignored

    shutil.copytree(source_root, staged_root, ignore=ignore_filter)


def _zip_directory(directory: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(directory))


def build_rootfs(source_root: Path, device_tree_path: Path, output_zip: Path) -> None:
    source_root = source_root.resolve()
    output_zip = output_zip.resolve()

    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"Source root does not exist or is not a directory: {source_root}")

    device_tree_data = _load_device_tree_data(device_tree_path)
    build_number = _increment_build_number(source_root / ".buildnum")

    with tempfile.TemporaryDirectory(prefix="deletescape_rootfs_") as temp_dir:
        staged_root = Path(temp_dir) / "deletescapeos"
        print(f"Copying source to temporary staging: {staged_root}")
        _copy_root_to_stage(source_root, staged_root, output_zip)

        print("Cleaning staged filesystem")
        _delete_directory_if_exists(staged_root / "logs")
        _clear_directory_contents(staged_root / "userdata")
        _remove_pycache_and_pyc(staged_root)

        config_json_path = staged_root / "config.json"
        if config_json_path.exists() and config_json_path.is_file():
            config_json_path.unlink()

        print("Copying defaults to root")
        _copy_defaults_to_root(staged_root)

        print("Updating osconfig builder metadata")
        _update_osconfig(staged_root, build_number=build_number)

        print("Writing deviceconfig from selected device tree")
        _write_deviceconfig(staged_root, device_tree_data)

        print(f"Creating output zip: {output_zip}")
        _zip_directory(staged_root, output_zip)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a DeletescapeOS rootfs zip from the current project and a selected device tree."
    )
    parser.add_argument(
        "--device-tree",
        help=(
            "Device tree path or name. Can be a directory containing deviceconfig.json "
            "or a JSON file. If omitted, an interactive selection prompt is shown "
            "for builder/device-trees."
        ),
    )
    parser.add_argument(
        "--source-root",
        default=str(_repo_root()),
        help="Source project root to copy into staging (default: repository root)",
    )
    parser.add_argument(
        "--output",
        default=str(_repo_root() / "output.zip"),
        help="Output zip path (default: <repo>/output.zip)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root)
    output_zip = Path(args.output)
    device_trees_root = _device_trees_root()

    try:
        device_tree_path = _resolve_device_tree_path(args.device_tree, device_trees_root)
        print(f"Using device tree: {device_tree_path}")
        build_rootfs(source_root=source_root, device_tree_path=device_tree_path, output_zip=output_zip)
    except Exception as exc:
        print(f"Build failed: {exc}")
        return 1

    print("Build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
