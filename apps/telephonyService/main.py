from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from logger import get_logger
from telephony import CallDirection, CallState, TextDirection, get_modem


log = get_logger("telephonyService")

APP_ID = "telephonyService"


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        container.setLayout(root)
        root.addWidget(QWidget(container))

        self._state_path = Path(__file__).resolve().parents[2] / "userdata" / "Data" / "System" / "Telephony" / "service_state.json"
        self._last_seen_incoming_ts = 0.0
        self._last_seen_incoming_ids_at_ts: set[str] = set()
        self._last_notified_call_key: str = ""

        self._load_state()

        self._modem = get_modem()

        # Push-based handlers. We keep the prior behavior of not notifying until
        # the first unlock.
        try:
            self._modem.text_received.connect(self._on_text_received)
        except Exception:
            log.exception("Failed to connect text_received signal")

        try:
            self._modem.call_updated.connect(self._on_call_updated)
        except Exception:
            log.exception("Failed to connect call_updated signal")

        # One-time catch-up for state on startup (no periodic polling).
        try:
            self._check_new_texts_from_history()
        except Exception:
            pass
        try:
            self._on_call_updated(self._modem.get_active_call())
        except Exception:
            pass

    def _load_state(self) -> None:
        try:
            if not self._state_path.exists():
                return
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return

            self._last_seen_incoming_ts = float(data.get("last_seen_incoming_ts") or 0.0)

            ids = data.get("last_seen_incoming_ids_at_ts")
            if isinstance(ids, list):
                self._last_seen_incoming_ids_at_ts = {str(x) for x in ids if x is not None}

            self._last_notified_call_key = str(data.get("last_notified_call_key") or "")
        except Exception:
            log.exception("Failed to load state")

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "last_seen_incoming_ts": float(self._last_seen_incoming_ts),
                "last_seen_incoming_ids_at_ts": sorted(self._last_seen_incoming_ids_at_ts),
                "last_notified_call_key": str(self._last_notified_call_key),
            }
            self._state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            log.exception("Failed to save state")

    def _has_unlocked_once(self) -> bool:
        try:
            fn = getattr(self.window, "has_unlocked_once", None)
            return bool(fn()) if callable(fn) else True
        except Exception:
            return True

    def _check_new_texts_from_history(self) -> None:
        getter = getattr(self._modem, "get_message_history", None)
        if not callable(getter):
            return

        try:
            hist = getter()
            messages = hist.list_messages()
        except Exception:
            return

        newest_ts = self._last_seen_incoming_ts
        newest_ids_at_ts: set[str] = set(self._last_seen_incoming_ids_at_ts)
        notified_any = False

        for msg in sorted(messages, key=lambda m: float(getattr(m, "timestamp_unix", 0.0))):
            try:
                if msg.direction != TextDirection.INCOMING:
                    continue
                ts = float(msg.timestamp_unix)
                if ts < self._last_seen_incoming_ts:
                    continue
                if ts == self._last_seen_incoming_ts and msg.id in self._last_seen_incoming_ids_at_ts:
                    continue

                # Notify and mark as seen.
                peer = str(getattr(msg, "peer", "") or "")
                body = str(getattr(msg, "body", "") or "")
                self.window.notify(
                    title=str(peer),
                    message=str(body),
                    duration_ms=3500,
                    app_id="messaging",
                )

                if ts > newest_ts:
                    newest_ts = ts
                    newest_ids_at_ts = {str(msg.id)}
                else:
                    newest_ids_at_ts.add(str(msg.id))

                notified_any = True
            except Exception:
                continue

        if notified_any:
            # Keep only a small set to avoid growth.
            self._last_seen_incoming_ts = float(newest_ts)
            self._last_seen_incoming_ids_at_ts = set(list(newest_ids_at_ts)[-25:])
            self._save_state()

    def _on_text_received(self, msg) -> None:
        if not self._has_unlocked_once():
            return

        try:
            if msg is None:
                return
            if getattr(msg, "direction", None) != TextDirection.INCOMING:
                return

            ts = float(getattr(msg, "timestamp_unix", 0.0) or 0.0)
            msg_id = str(getattr(msg, "id", "") or "")

            if ts < self._last_seen_incoming_ts:
                return
            if ts == self._last_seen_incoming_ts and msg_id in self._last_seen_incoming_ids_at_ts:
                return

            peer = str(getattr(msg, "peer", "") or "")
            body = str(getattr(msg, "body", "") or "")
            self.window.notify(
                title=str(peer),
                message=str(body),
                duration_ms=3500,
                app_id="messaging",
            )


            if ts > self._last_seen_incoming_ts:
                self._last_seen_incoming_ts = ts
                self._last_seen_incoming_ids_at_ts = {msg_id} if msg_id else set()
            else:
                if msg_id:
                    self._last_seen_incoming_ids_at_ts.add(msg_id)
                    # Keep only a small set to avoid growth.
                    self._last_seen_incoming_ids_at_ts = set(list(self._last_seen_incoming_ids_at_ts)[-25:])

            self._save_state()
        except Exception:
            return

    def _on_call_updated(self, call) -> None:
        if not self._has_unlocked_once():
            return

        if call is None:
            if self._last_notified_call_key:
                self._last_notified_call_key = ""
                self._save_state()
            return

        try:
            if call.direction != CallDirection.INCOMING:
                return
            if call.state != CallState.RINGING:
                return

            started = float(call.started_at_monotonic or 0.0)
            key = f"{call.number}:{started:.3f}"
            if key == self._last_notified_call_key:
                return

            self.window.notify(
                title="Incoming call",
                message=str(call.number or ""),
                duration_ms=3500,
                app_id="dialer",
            )
            self._last_notified_call_key = key
            self._save_state()
        except Exception:
            return
