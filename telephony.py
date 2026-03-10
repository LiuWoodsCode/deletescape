from __future__ import annotations

import json
import importlib
import math
import random
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from driver_config import get_device_driver_name
from logger import get_logger


log = get_logger("hal.telephony")


@dataclass(frozen=True)
class SignalStrength:
    """Best-effort cellular signal strength.

    `bars` is a normalized 0..4 value suitable for UI.
    `dbm` is optional and may be None on simulated/unknown providers.
    """

    bars: int
    dbm: int | None = None


def _bars_from_dbm(dbm: int | None) -> int:
    if dbm is None:
        return 0

    # Common LTE-ish mapping. We keep it intentionally simple.
    if dbm <= -110:
        return 0
    if dbm <= -100:
        return 1
    if dbm <= -90:
        return 2
    if dbm <= -80:
        return 3
    return 4


class CallDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class CallState(str, Enum):
    IDLE = "idle"
    DIALING = "dialing"
    RINGING = "ringing"
    CONNECTED = "connected"
    ENDED = "ended"
    FAILED = "failed"


class TextDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class TextStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass(frozen=True)
class CallInfo:
    number: str
    direction: CallDirection
    state: CallState
    started_at_monotonic: float | None = None
    connected_at_monotonic: float | None = None
    ended_at_monotonic: float | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class TextMessage:
    id: str
    peer: str
    direction: TextDirection
    body: str
    timestamp_unix: float
    status: TextStatus
    failure_reason: str | None = None

@dataclass(frozen=True)
class SimInfo:
    """Information describing the active SIM card."""
    iccid: str | None = None
    imsi: str | None = None
    operator_name: str | None = None
    mcc: str | None = None
    mnc: str | None = None
    phone_number: str | None = None


@dataclass(frozen=True)
class CellTowerInfo:
    """Describes a nearby or serving cell."""
    cell_id: int | None = None
    area_code: int | None = None       # LAC/TAC
    mcc: str | None = None
    mnc: str | None = None
    dbm: int | None = None
    frequency_mhz: float | None = None
    is_serving: bool = False

class MessageHistory:
    """JSON-backed message history.

    Stored at ./userdata/Data/System/Telephony/Messages/history.json as a list of message dicts.
    """

    def __init__(self, *, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent
        self._path = base_dir / "userdata" / "Data" / "System" / "Telephony" / "Messages" / "history.json"
        self._messages: list[TextMessage] = []
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        try:
            if not self._path.exists():
                self._messages = []
                return

            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                self._messages = []
                return

            parsed: list[TextMessage] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    parsed.append(
                        TextMessage(
                            id=str(item.get("id") or ""),
                            peer=str(item.get("peer") or ""),
                            direction=TextDirection(str(item.get("direction") or TextDirection.OUTGOING)),
                            body=str(item.get("body") or ""),
                            timestamp_unix=float(item.get("timestamp_unix") or 0.0),
                            status=TextStatus(str(item.get("status") or TextStatus.SENT)),
                            failure_reason=(str(item.get("failure_reason")) if item.get("failure_reason") is not None else None),
                        )
                    )
                except Exception:
                    continue

            # Keep only messages with a peer/id.
            self._messages = [m for m in parsed if m.id and m.peer]
        except Exception:
            log.exception("Failed to load message history", extra={"path": str(self._path)})
            self._messages = []

    def list_messages(self) -> list[TextMessage]:
        self.load()
        return list(self._messages)

    def append(self, msg: TextMessage) -> None:
        self.load()
        self._messages.append(msg)
        self._save()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(m) for m in self._messages]
            self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            log.exception("Failed to save message history", extra={"path": str(self._path)})


class ModemBase(QObject):
    """Minimal modem abstraction.

    This intentionally models only what the OS needs right now:
    a single active call and state transitions.
    """

    call_updated = Signal(object)  # emits CallInfo | None
    text_received = Signal(object)  # emits TextMessage
    text_sent = Signal(object)  # emits TextMessage

    def __init__(self):
        super().__init__()
        self._active_call: CallInfo | None = None

    def get_active_call(self) -> CallInfo | None:
        return self._active_call

    def dial(self, number: str) -> None:
        raise NotImplementedError

    def hang_up(self) -> None:
        raise NotImplementedError

    def send_text(self, peer: str, body: str) -> TextMessage | None:
        raise NotImplementedError

    def get_signal_strength(self) -> SignalStrength:
        """Return best-effort signal strength.

        Default implementation returns unknown/0 bars.
        """

        return SignalStrength(bars=0, dbm=None)

    def _set_call(self, info: CallInfo | None) -> None:
        self._active_call = info
        self.call_updated.emit(info)

    def get_sim_info(self) -> SimInfo:
        """Return best-effort SIM info."""
        return SimInfo()

    def get_serving_cell(self) -> CellTowerInfo | None:
        """Return the tower currently serving the modem."""
        return None

    def get_neighboring_cells(self) -> list[CellTowerInfo]:
        """Return a list of nearby cell towers."""
        return []


class SimulatedModem(ModemBase):
    """A fake modem for development.

    Behavior:
    - dial(number) -> DIALING, then CONNECTED after a short delay
    - hang_up() -> ENDED
    """

    def __init__(self, *, connect_delay_ms: int = 1300):
        super().__init__()
        self._connect_delay_ms = int(connect_delay_ms)
        self._pending_connect_timer: Optional[QTimer] = None
        self._pending_ring_timeout_timer: Optional[QTimer] = None
        self._history = MessageHistory()

        # Signal is simulated as a smooth fluctuation.
        # We don't run a timer for this; we just compute on demand.
        self._signal_seed = float(time.time())

        # Static fake SIM data
        self._sim_info = SimInfo(
            iccid="89014103211118510720",
            imsi="310260123456789",
            operator_name="SimuMobile",
            mcc="310",
            mnc="260",
            phone_number="+15551234567",
        )

    def get_sim_info(self) -> SimInfo:
        return self._sim_info

    def get_serving_cell(self) -> CellTowerInfo:
        strength = self.get_signal_strength()

        return CellTowerInfo(
            cell_id=12345,
            area_code=21011,
            mcc=self._sim_info.mcc,
            mnc=self._sim_info.mnc,
            dbm=strength.dbm,
            frequency_mhz=1850.0,
            is_serving=True,
        )

    def get_neighboring_cells(self) -> list[CellTowerInfo]:
        cells = []
        for i in range(3):
            dbm = -110 + int(20 * random.random())
            cells.append(
                CellTowerInfo(
                    cell_id=20000 + i,
                    area_code=21011,
                    mcc=self._sim_info.mcc,
                    mnc=self._sim_info.mnc,
                    dbm=dbm,
                    frequency_mhz=1850.0 + i * 5,
                    is_serving=False,
                )
            )
        return cells
    
    def get_signal_strength(self) -> SignalStrength:
        # A deterministic, smooth-ish waveform in [-112, -62] dBm.
        t = float(time.monotonic())
        # 30s period-ish.
        x = (t / 30.0) + (self._signal_seed % 1.0)
        wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * x)
        dbm = int(round(-112 + wave * 50))
        return SignalStrength(bars=_bars_from_dbm(dbm), dbm=dbm)

    def dial(self, number: str) -> None:
        number = (number or "").strip()
        if not number:
            log.info("Dial rejected: empty number")
            return

        # If there is already a call, hang it up first.
        if self._active_call is not None and self._active_call.state in {CallState.DIALING, CallState.RINGING, CallState.CONNECTED}:
            self.hang_up()

        now = time.monotonic()
        call = CallInfo(
            number=number,
            direction=CallDirection.OUTGOING,
            state=CallState.DIALING,
            started_at_monotonic=now,
        )
        log.info("Simulated dial", extra={"number": number})
        self._set_call(call)

        # Transition to CONNECTED after delay.
        self._cancel_pending_connect()
        self._pending_connect_timer = QTimer(self)
        self._pending_connect_timer.setSingleShot(True)
        self._pending_connect_timer.timeout.connect(self._connect_active_call)
        self._pending_connect_timer.start(self._connect_delay_ms)

    def simulate_incoming_call(self, number: str, *, ring_timeout_ms: int = 15000) -> CallInfo | None:
        """Simulate an incoming call (RINGING) for development."""
        number = (number or "").strip()
        if not number:
            return None

        # If there is already a call, hang it up first.
        if self._active_call is not None and self._active_call.state in {CallState.DIALING, CallState.RINGING, CallState.CONNECTED}:
            self.hang_up()

        self._cancel_pending_connect()
        self._cancel_pending_ring_timeout()

        now = time.monotonic()
        call = CallInfo(
            number=number,
            direction=CallDirection.INCOMING,
            state=CallState.RINGING,
            started_at_monotonic=now,
        )
        log.info("Simulated incoming call", extra={"number": number})
        self._set_call(call)

        # Auto-timeout to ENDED if not answered.
        self._pending_ring_timeout_timer = QTimer(self)
        self._pending_ring_timeout_timer.setSingleShot(True)
        self._pending_ring_timeout_timer.timeout.connect(self._ring_timeout)
        self._pending_ring_timeout_timer.start(max(250, int(ring_timeout_ms)))
        return call

    def _ring_timeout(self) -> None:
        self._pending_ring_timeout_timer = None
        if self._active_call is None:
            return
        if self._active_call.state != CallState.RINGING:
            return
        now = time.monotonic()
        updated = CallInfo(
            number=self._active_call.number,
            direction=self._active_call.direction,
            state=CallState.ENDED,
            started_at_monotonic=self._active_call.started_at_monotonic,
            connected_at_monotonic=self._active_call.connected_at_monotonic,
            ended_at_monotonic=now,
        )
        log.info("Simulated missed call", extra={"number": updated.number})
        self._set_call(updated)
        QTimer.singleShot(900, lambda: self._set_call(None))

    def _connect_active_call(self) -> None:
        self._pending_connect_timer = None
        if self._active_call is None:
            return
        if self._active_call.state != CallState.DIALING:
            return

        now = time.monotonic()
        updated = CallInfo(
            number=self._active_call.number,
            direction=self._active_call.direction,
            state=CallState.CONNECTED,
            started_at_monotonic=self._active_call.started_at_monotonic,
            connected_at_monotonic=now,
        )
        log.info("Simulated call connected", extra={"number": updated.number})
        self._set_call(updated)

    def hang_up(self) -> None:
        self._cancel_pending_connect()
        self._cancel_pending_ring_timeout()

        if self._active_call is None:
            return

        now = time.monotonic()
        updated = CallInfo(
            number=self._active_call.number,
            direction=self._active_call.direction,
            state=CallState.ENDED,
            started_at_monotonic=self._active_call.started_at_monotonic,
            connected_at_monotonic=self._active_call.connected_at_monotonic,
            ended_at_monotonic=now,
        )
        log.info("Simulated hangup", extra={"number": updated.number})
        self._set_call(updated)

        # Clear to IDLE shortly after so UIs can show "Call ended" briefly.
        QTimer.singleShot(900, lambda: self._set_call(None))

    def send_text(self, peer: str, body: str) -> TextMessage | None:
        peer = (peer or "").strip()
        body = (body or "").strip()
        if not peer:
            log.info("Send text rejected: empty peer")
            return None
        if not body:
            log.info("Send text rejected: empty body")
            return None

        msg = TextMessage(
            id=str(uuid.uuid4()),
            peer=peer,
            direction=TextDirection.OUTGOING,
            body=body,
            timestamp_unix=time.time(),
            status=TextStatus.SENT,
            failure_reason=None,
        )

        self._history.append(msg)
        self.text_sent.emit(msg)
        log.info("Simulated SMS sent", extra={"peer": peer, "len": len(body)})
        return msg

    def simulate_incoming_text(self, peer: str, body: str) -> TextMessage | None:
        peer = (peer or "").strip()
        body = (body or "").strip()
        if not peer or not body:
            return None

        msg = TextMessage(
            id=str(uuid.uuid4()),
            peer=peer,
            direction=TextDirection.INCOMING,
            body=body,
            timestamp_unix=time.time(),
            status=TextStatus.DELIVERED,
            failure_reason=None,
        )
        self._history.append(msg)
        self.text_received.emit(msg)
        log.info("Simulated SMS received", extra={"peer": peer, "len": len(body)})
        return msg

    def get_message_history(self) -> MessageHistory:
        return self._history

    def _cancel_pending_connect(self) -> None:
        try:
            if self._pending_connect_timer is not None:
                self._pending_connect_timer.stop()
                self._pending_connect_timer.deleteLater()
        except Exception:
            pass
        self._pending_connect_timer = None

    def _cancel_pending_ring_timeout(self) -> None:
        try:
            if self._pending_ring_timeout_timer is not None:
                self._pending_ring_timeout_timer.stop()
                self._pending_ring_timeout_timer.deleteLater()
        except Exception:
            pass
        self._pending_ring_timeout_timer = None


_default_modem: ModemBase | None = None
_default_modem_driver: str | None = None
_default_modem_lock = threading.Lock()


def get_modem() -> ModemBase:
    global _default_modem, _default_modem_driver

    driver_name = str(get_device_driver_name("modem", fallback="simulated")).strip().lower() or "simulated"

    with _default_modem_lock:
        if _default_modem is not None and _default_modem_driver == driver_name:
            return _default_modem

        _default_modem = _create_modem_from_driver(driver_name)
        _default_modem_driver = driver_name
        return _default_modem


def _create_modem_from_driver(driver_name: str) -> ModemBase:
    module_name = {
        "simulated": "drivers.modem.simulated",
        "none": "drivers.modem.none",
    }.get(str(driver_name or "").strip().lower(), "drivers.modem.none")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_modem", None)
        if callable(factory):
            modem = factory()
            if isinstance(modem, ModemBase):
                return modem
    except Exception:
        pass

    if driver_name == "simulated":
        return SimulatedModem()
    return _NoopModem()


class _NoopModem(ModemBase):
    def dial(self, number: str) -> None:
        return None

    def hang_up(self) -> None:
        return None

    def send_text(self, peer: str, body: str) -> TextMessage | None:
        return None


def get_signal_strength() -> SignalStrength:
    """Convenience API for UI code.

    Returns a best-effort signal strength from the active modem provider.
    """

    try:
        modem = get_modem()
        getter = getattr(modem, "get_signal_strength", None)
        if callable(getter):
            strength = getter()
            if isinstance(strength, SignalStrength):
                # Clamp bars defensively.
                bars = max(0, min(4, int(strength.bars)))
                return SignalStrength(bars=bars, dbm=strength.dbm)
            if isinstance(strength, dict):
                bars = max(0, min(4, int(strength.get("bars") or 0)))
                dbm = strength.get("dbm")
                return SignalStrength(bars=bars, dbm=(int(dbm) if dbm is not None else None))
    except Exception:
        pass

    return SignalStrength(bars=0, dbm=None)

