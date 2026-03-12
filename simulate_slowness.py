#!/usr/bin/env python3
"""
slow_launch.py
Launch a Python script under simulated performance constraints.

Supports:
- Device profiles (2018 smartwatch → 2026 flagship)
- Manual control via command-line (--line-delay, --import-delay, --io-delay)
- Monkeypatching for import & I/O slowdown
- sys.settrace for line-by-line CPU slowdown

Usage examples:
    python slow_launch.py --profile 2018-smartwatch app.py
    python slow_launch.py --line-delay 0.002 --io-delay 0.001 app.py
    python slow_launch.py --profile 2024-flagship --import-delay 0.01 app.py
"""

import sys
import time
import runpy
import builtins
import argparse


DEVICE_PROFILES = {
    "2015-smartwatch":  {"line_delay": 0.0025, "import_delay": 0.020,  "io_delay": 0.015},
    "2018-smartwatch":  {"line_delay": 0.0012, "import_delay": 0.010,  "io_delay": 0.006},
    "2017-budget-phone":{"line_delay": 0.0009, "import_delay": 0.008,  "io_delay": 0.004},
    "2020-budget-phone":{"line_delay": 0.0005, "import_delay": 0.004,  "io_delay": 0.002},
    "2020-midrange":    {"line_delay": 0.00025,"import_delay": 0.0025,"io_delay": 0.0012},
    "2023-midrange":    {"line_delay": 0.00018,"import_delay": 0.0018,"io_delay": 0.0008},
    "2022-flagship":    {"line_delay": 0.00010,"import_delay": 0.0010,"io_delay": 0.0005},
    "2024-flagship":    {"line_delay": 0.00005,"import_delay": 0.0006,"io_delay": 0.00025},
    "2026-flagship":    {"line_delay": 0.00003,"import_delay": 0.0003,"io_delay": 0.00015},
}


# --------------------------------------------------------------------
# Monkeypatch for imports & I/O slowdown
# --------------------------------------------------------------------
def apply_monkeypatch(import_delay, io_delay):
    real_import = builtins.__import__
    real_open = builtins.open

    def slow_import(name, globals=None, locals=None, fromlist=(), level=0):
        time.sleep(import_delay)
        return real_import(name, globals, locals, fromlist, level)

    def slow_open(*args, **kwargs):
        time.sleep(io_delay)
        return real_open(*args, **kwargs)

    builtins.__import__ = slow_import
    builtins.open = slow_open


# --------------------------------------------------------------------
# sys.settrace slowdown
# --------------------------------------------------------------------
def make_tracer(line_delay):
    def tracer(frame, event, arg):
        ## print(f"frame: {frame}\nevent: {event}\narg: {arg}")
        if event == "line":
            time.sleep(line_delay)
        return tracer
    return tracer


# --------------------------------------------------------------------
# CLI + Launcher
# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Simulate device performance throttling.")

    parser.add_argument("target", help="Python script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER)

    parser.add_argument("--profile", help="Device performance profile")

    # Manual overrides
    parser.add_argument("--line-delay", type=float, help="Override line-by-line CPU delay")
    parser.add_argument("--import-delay", type=float, help="Override module import delay")
    parser.add_argument("--io-delay", type=float, help="Override file I/O delay")

    args = parser.parse_args()

    # ----------------------------------------------------------------
    # Build final settings from profile + overrides
    # ----------------------------------------------------------------
    if args.profile:
        if args.profile not in DEVICE_PROFILES:
            print("Unknown profile. Available:")
            for p in DEVICE_PROFILES:
                print(" ", p)
            sys.exit(1)

        profile = DEVICE_PROFILES[args.profile].copy()
    else:
        # No profile used → start from zeroes
        profile = {"line_delay": 0.0, "import_delay": 0.0, "io_delay": 0.0}

    # Apply user overrides
    if args.line_delay     is not None: profile["line_delay"]     = args.line_delay
    if args.import_delay   is not None: profile["import_delay"]   = args.import_delay
    if args.io_delay       is not None: profile["io_delay"]       = args.io_delay

    # ----------------------------------------------------------------
    # Apply throttling
    # ----------------------------------------------------------------
    if not args.import_delay == 0:
        apply_monkeypatch(profile["import_delay"], profile["io_delay"])

    if not args.line_delay == 0:
        tracer_fn = make_tracer(profile["line_delay"])
        sys.settrace(tracer_fn)

    # Set target script args
    sys.argv = [args.target] + args.args

    # Run
    runpy.run_path(args.target, run_name="__main__")


if __name__ == "__main__":
    main()