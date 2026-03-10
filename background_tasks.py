from __future__ import annotations

import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from logger import get_logger


log = get_logger("background_tasks")


BackgroundCallback = Callable[[], None]


@dataclass
class BackgroundTaskHandle:
    task_id: int
    app_id: str
    name: str
    interval_ms: int


@dataclass
class _TaskEntry:
    handle: BackgroundTaskHandle
    timer: QTimer
    callback: BackgroundCallback
    in_flight: bool = False
    canceled: bool = False


class BackgroundTaskManager(QObject):
    """Runs lightweight periodic callbacks for apps.

    This is intentionally simple and UI-thread-only:
    - Uses QTimer, so callbacks run on the Qt event loop thread.
    - Catches exceptions so one bad task doesn't kill the shell.

    Tasks are allowed only after the first unlock.
    """

    def __init__(self, *, window):
        super().__init__(window)
        self._window = window
        self._next_id = 1
        self._lock = threading.RLock()
        self._tasks: dict[int, _TaskEntry] = {}

        # Keep this small: these are "background" helpers, not heavy compute.
        max_workers = max(2, min(8, int(os.cpu_count() or 4)))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bg")

    def shutdown(self) -> None:
        try:
            self._executor.shutdown(wait=False, cancel_futures=False)
        except Exception:
            pass

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass

    def _run_task(self, *, task_id: int, app_id: str, task_name: str, callback: BackgroundCallback) -> None:
        try:
            t0 = time.perf_counter()
            callback()
            dt_ms = int((time.perf_counter() - t0) * 1000)
            log.debug(
                "Background task ran",
                extra={"task_id": task_id, "app_id": str(app_id), "task_name": str(task_name), "dt_ms": dt_ms},
            )
        except Exception:
            # Never crash the shell from a background callback.
            try:
                log.exception(
                    "Background task crashed",
                    extra={"task_id": task_id, "app_id": str(app_id), "task_name": str(task_name)},
                )
            except Exception:
                pass

            # Disable this task to avoid a crash loop (must happen on UI thread).
            try:
                run_ui = getattr(self._window, "run_on_ui_thread", None)
                if callable(run_ui):
                    run_ui(lambda: self.cancel(task_id))
                else:
                    self.cancel(task_id)
            except Exception:
                pass

            # Surface a lightweight notification if supported.
            try:
                notify = getattr(self._window, "notify", None)
                if callable(notify):
                    notify(
                        title="App error",
                        message=f"{task_name} background task crashed",
                        duration_ms=3500,
                        app_id="system",
                    )
            except Exception:
                pass
        finally:
            try:
                with self._lock:
                    entry = self._tasks.get(int(task_id))
                    if entry is not None:
                        entry.in_flight = False
            except Exception:
                pass

    def register(
        self,
        *,
        app_id: str,
        callback: BackgroundCallback,
        interval_ms: int = 1000,
        name: str = "background_task",
        start_immediately: bool = False,
    ) -> BackgroundTaskHandle:
        interval_ms = max(50, int(interval_ms))

        task_id = self._next_id
        self._next_id += 1

        handle = BackgroundTaskHandle(
            task_id=task_id,
            app_id=str(app_id),
            name=str(name),
            interval_ms=interval_ms,
        )

        timer = QTimer(self)
        timer.setInterval(interval_ms)

        log.debug(
            "Register background task",
            extra={
                "task_id": task_id,
                "app_id": str(app_id),
                "task_name": str(name),
                "interval_ms": interval_ms,
                "start_immediately": bool(start_immediately),
            },
        )

        def _run_once() -> None:
            # Enforce: no background tasks before first unlock.
            try:
                if not bool(getattr(self._window, "has_unlocked_once", lambda: False)()):
                    log.debug(
                        "Skipping background task (locked)",
                        extra={"task_id": task_id, "app_id": str(app_id), "task_name": str(name)},
                    )
                    return
            except Exception:
                log.exception(
                    "Failed to evaluate unlock state for background task",
                    extra={"task_id": task_id, "app_id": str(app_id), "task_name": str(name)},
                )
                return

            # Execute callback on a worker thread.
            try:
                with self._lock:
                    entry = self._tasks.get(int(task_id))
                    if entry is None or entry.canceled:
                        return
                    if entry.in_flight:
                        log.debug(
                            "Skipping background task (still running)",
                            extra={"task_id": task_id, "app_id": str(app_id), "task_name": str(name)},
                        )
                        return
                    entry.in_flight = True

                self._executor.submit(self._run_task, task_id=int(task_id), app_id=str(app_id), task_name=str(name), callback=callback)
            except Exception:
                # If scheduling fails, clear the in-flight flag so we don't wedge.
                try:
                    with self._lock:
                        entry = self._tasks.get(int(task_id))
                        if entry is not None:
                            entry.in_flight = False
                except Exception:
                    pass

        timer.timeout.connect(_run_once)

        with self._lock:
            self._tasks[task_id] = _TaskEntry(handle=handle, timer=timer, callback=callback)

        if start_immediately:
            QTimer.singleShot(0, _run_once)

        # Start even if locked; gating is done in _run_once.
        timer.start()
        return handle

    def cancel(self, task_id: int) -> None:
        with self._lock:
            entry = self._tasks.pop(int(task_id), None)
        if entry is None:
            return

        entry.canceled = True
        timer = entry.timer

        log.debug("Cancel background task", extra={"task_id": int(task_id)})
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass

    def cancel_for_app(self, app_id: str) -> None:
        app_id = str(app_id)
        with self._lock:
            to_cancel = [tid for tid, e in self._tasks.items() if e.handle.app_id == app_id]

        log.debug(
            "Cancel tasks for app",
            extra={"app_id": app_id, "count": len(to_cancel), "task_ids": list(to_cancel)},
        )
        for tid in to_cancel:
            self.cancel(tid)

    def cancel_all(self) -> None:
        with self._lock:
            tids = list(self._tasks.keys())
        log.debug("Cancel all background tasks", extra={"count": len(tids)})
        for tid in tids:
            self.cancel(tid)
