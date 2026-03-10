from __future__ import annotations

import sys
import threading
import traceback
from typing import Callable

from logger import get_logger


def install_exception_hooks(report_crash: Callable[[type[BaseException], BaseException, object | None], None]) -> None:
    """Install global exception hooks.

    PyQt will typically route unhandled exceptions from slots/callbacks through
    sys.excepthook; this ensures we can show a message box and recover back to
    Home rather than silently breaking the app.

    report_crash(exc_type, exc, tb) is expected to be UI-safe (it may schedule
    onto the Qt event loop).
    """

    previous_sys_hook = sys.excepthook
    log = get_logger("crash")

    def _sys_hook(exc_type, exc, tb):
        try:
            # Always log a traceback for debugging.
            log.exception(
                "Unhandled exception (sys.excepthook)",
                exc_info=(exc_type, exc, tb),
            )
        except Exception:
            pass

        try:
            report_crash(exc_type, exc, tb)
        except Exception:
            # Never let crash reporting crash the process.
            try:
                previous_sys_hook(exc_type, exc, tb)
            except Exception:
                pass

    sys.excepthook = _sys_hook

    # Python 3.8+: catch unhandled exceptions in background threads.
    if hasattr(threading, "excepthook"):
        previous_thread_hook = threading.excepthook

        def _thread_hook(args):
            try:
                log.exception(
                    "Unhandled exception (threading.excepthook)",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
            except Exception:
                pass
            try:
                report_crash(args.exc_type, args.exc_value, args.exc_traceback)
            except Exception:
                try:
                    previous_thread_hook(args)
                except Exception:
                    pass

        threading.excepthook = _thread_hook
