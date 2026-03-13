#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import shutil
import os

# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER = REPO_ROOT / "builder" / "build_rootfs.py"

# ------------------------------------------------------------
# BUILD + RUN
# ------------------------------------------------------------

def run_build_and_boot(device_tree: str | None, debug: bool) -> int:

    if not BUILDER.exists():
        print(f"Builder not found at {BUILDER}")
        return 1

    with tempfile.TemporaryDirectory(prefix="deletescape_test_") as tmp:

        tmp = Path(tmp)

        zip_out = tmp / "rootfs.zip"
        extract_dir = tmp / "rootfs"

        print("\n=== Running Builder ===")

        build_cmd = [
            sys.executable,
            str(BUILDER),
            "--source-root",
            str(REPO_ROOT),
            "--output",
            str(zip_out),
        ]

        if device_tree:
            build_cmd += ["--device-tree", device_tree]

        if debug:
            build_cmd.append("--debug")

        result = subprocess.run(build_cmd)

        if result.returncode != 0:
            print("\nBuild failed.")
            return result.returncode

        if not zip_out.exists():
            print("\nBuild did not produce zip.")
            return 1

        print("\n=== Extracting RootFS ===")

        extract_dir.mkdir()

        with zipfile.ZipFile(zip_out, "r") as z:
            z.extractall(extract_dir)

        boot_py = extract_dir / "boot.py"

        if not boot_py.exists():
            print("\nboot.py not found at root of built filesystem!")
            return 1

        print("\n=== Booting Built RootFS ===\n")

        # Important: run inside extracted rootfs
        env = os.environ.copy()
        env["PYTHONPATH"] = str(extract_dir)

        return subprocess.run(
            [sys.executable, str(boot_py)],
            cwd=extract_dir,
            env=env
        ).returncode


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--device-tree")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    return run_build_and_boot(
        device_tree=args.device_tree,
        debug=args.debug
    )


if __name__ == "__main__":
    raise SystemExit(main())