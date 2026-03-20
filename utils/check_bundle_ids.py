#!/usr/bin/env python3
"""
Check manifests under an apps/ directory and verify the bundle ID key is exactly "bundleID".

Usage:
    python check_bundleID_form.py [--apps-root PATH]

Exit codes:
  0 - all apps use the exact "bundleID" key with a non-empty value
  1 - one or more apps use an incorrect key form, empty value, or are missing a manifest
  2 - apps root not found or not a directory
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Tuple, List

ALLOWED_KEY = "bundleId"


def read_manifest(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def inspect_manifest(manifest: dict) -> Tuple[str, Optional[str]]:
    """
    Returns a tuple (status, value_or_note) where status is one of:
      - "valid" (manifest contains ALLOWED_KEY with non-empty string)
      - "wrong_key" (manifest contains other known key forms)
      - "empty" (ALLOWED_KEY present but empty/non-string)
      - "missing" (none of the known keys present)
    and value_or_note holds the actual value (if any) or an explanatory note.
    """
    # Direct check for exact allowed key (case-sensitive)
    if ALLOWED_KEY in manifest:
        val = manifest.get(ALLOWED_KEY)
        if isinstance(val, str) and val.strip():
            return "valid", val.strip()
        # present but empty/non-string
        return "empty", str(val)

    # Check for incorrect variants (common alternatives)
    for k in ("bundleID", "bundle_id", "bundle", "bundleID"):
        if k in manifest:
            val = manifest.get(k)
            return "wrong_key", f"{k}={val!r}"

    # No keys found
    return "missing", None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that Deletescape app manifests use bundleID (exact key).")
    parser.add_argument("--apps-root", "-r", default="apps", help="Path to apps/ directory (default: ./apps)")
    args = parser.parse_args()

    apps_root = Path(args.apps_root)
    if not apps_root.exists() or not apps_root.is_dir():
        print(f"Error: apps root not found or not a directory: {apps_root}", file=sys.stderr)
        return 2

    any_issues = False
    results: List[Tuple[str, str, Optional[str], Optional[str]]] = []
    # (folder, status, value_or_note, display_name/appId)

    for entry in sorted(apps_root.iterdir(), key=lambda p: p.name.lower()):
        # Exclude __pycache__ folders from being checked
        if entry.name == "__pycache__":
            continue

        if not entry.is_dir():
            continue

        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            results.append((entry.name, "no_manifest", None, None))
            any_issues = True
            continue

        manifest = read_manifest(manifest_path)
        if manifest is None:
            results.append((entry.name, "bad_manifest", None, None))
            any_issues = True
            continue

        # friendly id/displayName
        display = manifest.get("displayName") or manifest.get("appId") or manifest.get("id") or manifest.get("app_id")
        display = str(display).strip() if display is not None else None

        status, val = inspect_manifest(manifest)
        if status != "valid":
            any_issues = True
        results.append((entry.name, status, val, display))

    # Print per-app results
    print("App bundleID key validation (accepted key must be exactly: 'bundleID')\n")
    for folder, status, val, display in results:
        label = f" ({display})" if display else ""
        if status == "valid":
            print(f"[OK]     {folder}{label}: uses 'bundleId' = {val!r}")
        elif status == "wrong_key":
            print(f"[WRONG]  {folder}{label}: uses incorrect key -> {val}")
        elif status == "empty":
            print(f"[EMPTY]  {folder}{label}: 'bundleId' present but empty/non-string -> {val!r}")
        elif status == "no_manifest":
            print(f"[NO MAN] {folder}: missing manifest.json")
        elif status == "bad_manifest":
            print(f"[BAD]    {folder}{label}: manifest.json exists but failed to parse")
        elif status == "missing":
            print(f"[MISS]   {folder}{label}: no bundle key found (expected 'bundleId')")
        else:
            print(f"[?]      {folder}{label}: status={status} value={val!r}")

    print()
    if any_issues:
        print("Result: Issues detected. Fix manifests so the exact key 'bundleID' (case-sensitive) is present with a non-empty string value.")
        return 1
    print("Result: All apps use the exact 'bundleID' key with non-empty values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())