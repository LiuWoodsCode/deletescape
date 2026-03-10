from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)


DEFAULT_LAT = 40.7128
DEFAULT_LON = -74.0060


SEP = " \u2022 "


@dataclass
class WeatherSettings:
    lat: float = DEFAULT_LAT
    lon: float = DEFAULT_LON
    user_agent: str = ""


def _userdata_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "userdata"


def _settings_path() -> Path:
    return _userdata_dir() / "Data" / "Application" / "weather" / "config.json"


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_settings() -> WeatherSettings:
    p = _settings_path()
    if not p.exists():
        return WeatherSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return WeatherSettings()
        return WeatherSettings(
            lat=_coerce_float(data.get("lat"), DEFAULT_LAT),
            lon=_coerce_float(data.get("lon"), DEFAULT_LON),
            user_agent=str(data.get("user_agent") or ""),
        )
    except Exception:
        return WeatherSettings()


def _save_settings(s: WeatherSettings) -> None:
    settings_path = _settings_path()
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    payload = {"lat": float(s.lat), "lon": float(s.lon), "user_agent": str(s.user_agent or "")}
    settings_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fmt_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        try:
            return value.strftime("%a %I:%M %p")
        except Exception:
            return ""
    try:
        return str(value)
    except Exception:
        return ""


def _first_nonempty(*values: Any) -> str:
    for v in values:
        try:
            s = str(v or "").strip()
        except Exception:
            s = ""
        if s:
            return s
    return ""


def _format_temp(temp: Any, unit: Any) -> str:
    t = _first_nonempty(temp)
    u = _first_nonempty(unit)
    if not t:
        return "--"
    if u:
        return f"{t}{u}"
    return t


def _guess_place_name(point: Any) -> str:
    # `nws_ez` object shape may vary; try a few common patterns.
    for candidate in (
        getattr(point, "city", None),
        getattr(point, "name", None),
    ):
        s = _first_nonempty(candidate)
        if s:
            return s

    # Try relative location containers.
    for rel in (
        getattr(point, "relative_location", None),
        getattr(point, "relativeLocation", None),
    ):
        if rel is None:
            continue
        city = _first_nonempty(getattr(rel, "city", None), getattr(rel, "City", None))
        state = _first_nonempty(getattr(rel, "state", None), getattr(rel, "State", None))
        if city and state:
            return f"{city}, {state}"
        if city:
            return city

        props = getattr(rel, "properties", None)
        if isinstance(props, dict):
            city = _first_nonempty(props.get("city"), props.get("City"))
            state = _first_nonempty(props.get("state"), props.get("State"))
            if city and state:
                return f"{city}, {state}"
            if city:
                return city

    props = getattr(point, "properties", None)
    if isinstance(props, dict):
        city = _first_nonempty(props.get("city"), props.get("City"))
        state = _first_nonempty(props.get("state"), props.get("State"))
        if city and state:
            return f"{city}, {state}"
        if city:
            return city

    return ""


class _FetchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, lat: float, lon: float, user_agent: str):
        super().__init__()
        self._lat = float(lat)
        self._lon = float(lon)
        self._ua = str(user_agent or "")

    def run(self) -> None:
        try:
            from nws_ez import NWSClient

            ua = self._ua.strip() or os.environ.get("NWS_USER_AGENT", "").strip()
            if not ua:
                ua = "Deletescape-Weather/0.1"

            client = NWSClient(user_agent=ua)

            point = client.point(self._lat, self._lon)
            forecast = client.forecast(self._lat, self._lon)
            hourly = client.hourly(self._lat, self._lon)
            alerts = client.alerts_active(point=(self._lat, self._lon))

            self.finished.emit(
                {
                    "point": point,
                    "forecast": forecast,
                    "hourly": hourly,
                    "alerts": alerts,
                    "user_agent": ua,
                }
            )
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self.failed.emit(msg)


class App:
    def __init__(self, window, container):
        self.window = window
        self.container = container

        self._settings = _load_settings()
        self._active_mode = "forecast"  # forecast | hourly | alerts

        self._data: dict[str, Any] | None = None
        self._thread: QThread | None = None
        self._worker: _FetchWorker | None = None
        self._closing: bool = False

        root = QVBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        container.setLayout(root)

        # Header / current conditions panel (kept simple + touch-friendly).
        self._place_title = QLabel("Weather")
        self._place_title.setAlignment(Qt.AlignCenter)
        place_font = QFont()
        place_font.setPointSize(18)
        place_font.setBold(True)
        self._place_title.setFont(place_font)
        root.addWidget(self._place_title)

        self._subtitle = QLabel("")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)

        self._updated_label = QLabel("")
        self._updated_label.setAlignment(Qt.AlignCenter)
        self._updated_label.setWordWrap(True)
        root.addWidget(self._updated_label)

        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        root.addLayout(current_row)

        self._temp_label = QLabel("--")
        self._temp_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        temp_font = QFont()
        temp_font.setPointSize(44)
        temp_font.setBold(True)
        self._temp_label.setFont(temp_font)
        current_row.addWidget(self._temp_label, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        current_row.addLayout(right, 1)

        self._cond_label = QLabel("Tap Refresh")
        self._cond_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._cond_label.setWordWrap(True)
        cond_font = QFont()
        cond_font.setPointSize(14)
        cond_font.setBold(True)
        self._cond_label.setFont(cond_font)
        right.addWidget(self._cond_label)

        self._hilow_label = QLabel("")
        self._hilow_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._hilow_label.setWordWrap(True)
        right.addWidget(self._hilow_label)

        self._meta_label = QLabel("")
        self._meta_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._meta_label.setWordWrap(True)
        right.addWidget(self._meta_label)

        # Mode buttons (touch friendly)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        root.addLayout(mode_row)

        self._btn_forecast = QPushButton("Forecast")
        self._btn_forecast.setMinimumHeight(44)
        self._btn_forecast.clicked.connect(lambda: self._set_mode("forecast"))
        mode_row.addWidget(self._btn_forecast)

        self._btn_hourly = QPushButton("Hourly")
        self._btn_hourly.setMinimumHeight(44)
        self._btn_hourly.clicked.connect(lambda: self._set_mode("hourly"))
        mode_row.addWidget(self._btn_hourly)

        self._btn_alerts = QPushButton("Alerts")
        self._btn_alerts.setMinimumHeight(44)
        self._btn_alerts.clicked.connect(lambda: self._set_mode("alerts"))
        mode_row.addWidget(self._btn_alerts)

        self._stack = QStackedLayout()
        root.addLayout(self._stack, 1)

        self._list_view = self._build_list_view()
        self._detail_view = self._build_detail_view()

        self._stack.addWidget(self._list_view)
        self._stack.addWidget(self._detail_view)
        self._stack.setCurrentWidget(self._list_view)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        root.addLayout(bottom)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setMinimumHeight(44)
        self._refresh_btn.clicked.connect(self.refresh)
        bottom.addWidget(self._refresh_btn)

        self._location_btn = QPushButton("Location")
        self._location_btn.setMinimumHeight(44)
        self._location_btn.clicked.connect(self._open_location)
        bottom.addWidget(self._location_btn)

        self._set_mode(self._active_mode)
        self._sync_subtitle()
        self.refresh()

    def on_quit(self) -> None:
        # The shell may delete our container immediately after on_quit.
        # Ensure no background-thread callbacks try to touch deleted widgets,
        # and avoid Qt destroying a running QThread via parent-child teardown.
        self._closing = True

        worker = self._worker
        thread = self._thread
        if worker is not None:
            try:
                worker.finished.disconnect(self._on_data)
            except Exception:
                pass
            try:
                worker.failed.disconnect(self._on_error)
            except Exception:
                pass

        if thread is not None:
            try:
                # If the thread was parented, detach it so deletion of the app
                # container can't destroy a running thread object.
                thread.setParent(None)
            except Exception:
                pass

    # -------------------- Views --------------------
    def _build_list_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        w.setLayout(layout)

        self._list = QListWidget()
        self._list.itemActivated.connect(self._open_selected_detail)
        layout.addWidget(self._list, 1)

        return w

    def _build_detail_view(self) -> QWidget:
        w = QWidget(self.container)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        w.setLayout(layout)

        self._detail_title = QLabel("")
        self._detail_title.setAlignment(Qt.AlignCenter)
        self._detail_title.setWordWrap(True)
        df = QFont()
        df.setPointSize(16)
        df.setBold(True)
        self._detail_title.setFont(df)
        layout.addWidget(self._detail_title)

        self._detail_body = QLabel("")
        self._detail_body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._detail_body.setWordWrap(True)
        self._detail_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._detail_body, 1)

        back = QPushButton("Back")
        back.setMinimumHeight(44)
        back.clicked.connect(self._back_to_list)
        layout.addWidget(back)

        return w

    def _back_to_list(self) -> None:
        self._stack.setCurrentWidget(self._list_view)

    def _open_selected_detail(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        payload = item.data(Qt.UserRole)
        if not isinstance(payload, dict):
            return
        title = str(payload.get("title") or "")
        body = str(payload.get("body") or "")
        self._detail_title.setText(title)
        self._detail_body.setText(body)
        self._stack.setCurrentWidget(self._detail_view)

    def _set_mode(self, mode: str) -> None:
        mode = str(mode)
        if mode not in ("forecast", "hourly", "alerts"):
            mode = "forecast"
        self._active_mode = mode

        # Visual hint: disable current mode button.
        self._btn_forecast.setEnabled(mode != "forecast")
        self._btn_hourly.setEnabled(mode != "hourly")
        self._btn_alerts.setEnabled(mode != "alerts")

        self._render_list()

    # -------------------- Location --------------------
    def _sync_subtitle(self) -> None:
        lat = float(self._settings.lat)
        lon = float(self._settings.lon)
        self._subtitle.setText(f"Lat {lat:.4f}, Lon {lon:.4f}")

    def _open_location(self) -> None:
        # Simple in-place editor using the detail screen.
        self._detail_title.setText("Location")

        ua = (self._settings.user_agent or "").strip() or os.environ.get("NWS_USER_AGENT", "").strip()
        ua_hint = "(set)" if ua else "(missing)"

        body = (
            "Enter coordinates (decimal degrees) then tap Apply.\n\n"
            f"Current: {float(self._settings.lat):.4f}, {float(self._settings.lon):.4f}\n"
            f"User-Agent: {ua_hint}\n"
            "\n"
            "Note: NWS requires a real contact User-Agent.\n"
        )
        self._detail_body.setText(body)

        # Replace detail view content with inputs by rebuilding minimal widgets.
        # Keep it simple: we create an ad-hoc layout section at the top.
        parent_layout = self._detail_view.layout()
        if parent_layout is None:
            return

        # Remove existing input row if present.
        for name in ("_loc_row_widget",):
            old = getattr(self, name, None)
            if isinstance(old, QWidget):
                old.setParent(None)
                old.deleteLater()

        row = QWidget(self._detail_view)
        row_layout = QVBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row.setLayout(row_layout)

        self._lat_in = QLineEdit()
        self._lat_in.setPlaceholderText("Latitude (e.g. 40.7128)")
        self._lat_in.setText(str(self._settings.lat))
        row_layout.addWidget(self._lat_in)

        self._lon_in = QLineEdit()
        self._lon_in.setPlaceholderText("Longitude (e.g. -74.0060)")
        self._lon_in.setText(str(self._settings.lon))
        row_layout.addWidget(self._lon_in)

        self._ua_in = QLineEdit()
        self._ua_in.setPlaceholderText("Optional User-Agent override")
        self._ua_in.setText(str(self._settings.user_agent or ""))
        row_layout.addWidget(self._ua_in)

        apply_btn = QPushButton("Apply")
        apply_btn.setMinimumHeight(44)
        apply_btn.clicked.connect(self._apply_location)
        row_layout.addWidget(apply_btn)

        # Insert right after title label.
        parent_layout.insertWidget(1, row)
        self._loc_row_widget = row

        self._stack.setCurrentWidget(self._detail_view)

    def _apply_location(self) -> None:
        try:
            lat = float((self._lat_in.text() or "").strip())
            lon = float((self._lon_in.text() or "").strip())
        except Exception:
            self.window.notify(title="Weather", message="Invalid coordinates", duration_ms=1800, app_id="weather")
            return

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            self.window.notify(title="Weather", message="Coordinates out of range", duration_ms=2000, app_id="weather")
            return

        ua = str((self._ua_in.text() or "").strip())

        self._settings = WeatherSettings(lat=lat, lon=lon, user_agent=ua)
        try:
            _save_settings(self._settings)
        except Exception:
            pass

        self._sync_subtitle()
        self._back_to_list()
        self.refresh()

    # -------------------- Data fetch/render --------------------
    def refresh(self) -> None:
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    return
            except Exception:
                pass

        self._cond_label.setText("Loading…")
        self._temp_label.setText("--")
        self._hilow_label.setText("")
        self._meta_label.setText("")
        self._refresh_btn.setEnabled(False)

        # Important: do not parent the QThread to `self.container`.
        # When the user presses Home, the shell may delete the container widget.
        # If the QThread is a child, Qt will destroy it even if still running,
        # which can crash the whole process.
        self._thread = QThread()
        self._worker = _FetchWorker(self._settings.lat, self._settings.lon, self._settings.user_agent)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data)
        self._worker.failed.connect(self._on_error)

        # Always cleanup.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        def _clear_thread_refs() -> None:
            # Avoid holding onto finished threads (and allow repeated refresh).
            self._thread = None
            self._worker = None

        self._thread.finished.connect(_clear_thread_refs)

        self._thread.start()

    def _on_error(self, message: str) -> None:
        if self._closing:
            return
        self._refresh_btn.setEnabled(True)
        self._cond_label.setText("Refresh failed")

        try:
            self.window.notify(title="Weather", message=str(message or "Error"), duration_ms=3500, app_id=weather)
        except Exception:
            pass

    def _on_data(self, data: object) -> None:
        if self._closing:
            return
        self._refresh_btn.setEnabled(True)
        if not isinstance(data, dict):
            self._on_error("Bad response")
            return

        self._data = data

        # Update header (place + current conditions).
        try:
            point = data.get("point")
            place = _guess_place_name(point)
            self._place_title.setText(place or "Weather")
        except Exception:
            self._place_title.setText("Weather")

        try:
            now = datetime.now()
            self._updated_label.setText(f"Updated {now.strftime('%a %I:%M %p')}")
        except Exception:
            self._updated_label.setText("Updated")

        try:
            forecast = data.get("forecast")
            periods = getattr(forecast, "periods", []) or []
            if periods:
                p0 = periods[0]
                temp = getattr(p0, "temperature", None)
                unit = getattr(p0, "temperature_unit", None)
                short = getattr(p0, "short_forecast", None)
                wind_speed = getattr(p0, "wind_speed", None)
                wind_dir = getattr(p0, "wind_direction", None)
                pop = getattr(p0, "probability_of_precipitation", None)

                self._temp_label.setText(_format_temp(temp, unit))
                self._cond_label.setText(_first_nonempty(short, ""))

                # Hi/lo: take first two forecast periods as a pragmatic approximation.
                t0 = _first_nonempty(getattr(periods[0], "temperature", None))
                t1 = _first_nonempty(getattr(periods[1], "temperature", None)) if len(periods) > 1 else ""
                u0 = _first_nonempty(getattr(periods[0], "temperature_unit", None), unit)
                if t0 and t1 and u0:
                    self._hilow_label.setText(f"Hi/Lo: {t0}{u0} / {t1}{u0}")
                else:
                    self._hilow_label.setText("")

                meta_parts: list[str] = []
                wind = _first_nonempty(wind_speed)
                wdir = _first_nonempty(wind_dir)
                if wind and wdir:
                    meta_parts.append(f"Wind {wind} {wdir}")
                elif wind:
                    meta_parts.append(f"Wind {wind}")
                if pop is not None:
                    meta_parts.append(f"Precip {pop}")
                # Alerts count hint.
                try:
                    alerts = data.get("alerts")
                    features = getattr(alerts, "features", []) or []
                    if features:
                        meta_parts.append(f"Alerts {len(features)}")
                except Exception:
                    pass

                self._meta_label.setText(SEP.join([p for p in meta_parts if p]))
            else:
                self._temp_label.setText("--")
                self._cond_label.setText("Updated")
                self._hilow_label.setText("")
                self._meta_label.setText("")
        except Exception:
            self._temp_label.setText("--")
            self._cond_label.setText("Updated")
            self._hilow_label.setText("")
            self._meta_label.setText("")

        self._render_list()

    def _render_list(self) -> None:
        self._list.clear()

        if self._data is None:
            self._list.addItem(QListWidgetItem("Tap Refresh to load weather"))
            return

        mode = self._active_mode

        if mode == "forecast":
            self._render_forecast()
            return

        if mode == "hourly":
            self._render_hourly()
            return

        if mode == "alerts":
            self._render_alerts()
            return

    def _render_forecast(self) -> None:
        forecast = (self._data or {}).get("forecast")
        periods = getattr(forecast, "periods", []) or []
        if not periods:
            self._list.addItem(QListWidgetItem("No forecast periods"))
            return

        for p in periods:
            name = str(getattr(p, "name", "") or "")
            temp = getattr(p, "temperature", "")
            unit = str(getattr(p, "temperature_unit", "") or "")
            short = str(getattr(p, "short_forecast", "") or "")
            wind = f"{getattr(p, 'wind_speed', '')} {getattr(p, 'wind_direction', '')}".strip()
            pop = getattr(p, "probability_of_precipitation", None)

            line1 = f"{name}{SEP}{temp}{unit}".strip()
            sub_parts: list[str] = []
            if short:
                sub_parts.append(short)
            if pop is not None:
                sub_parts.append(f"Precip {pop}")
            if wind:
                sub_parts.append(f"Wind {wind}")
            line2 = SEP.join(sub_parts)
            line3 = ""

            body = str(getattr(p, "detailed_forecast", "") or "")
            payload = {
                "title": line1,
                "body": "\n".join([x for x in [line2, "", body] if x]).strip(),
            }

            item = QListWidgetItem("\n".join([x for x in (line1, line2, line3) if x]))
            item.setData(Qt.UserRole, payload)
            self._list.addItem(item)

    def _render_hourly(self) -> None:
        hourly = (self._data or {}).get("hourly")
        periods = getattr(hourly, "periods", []) or []
        if not periods:
            self._list.addItem(QListWidgetItem("No hourly periods"))
            return

        for p in periods[:24]:
            ts = _fmt_dt(getattr(p, "start_time", None))
            temp = getattr(p, "temperature", "")
            unit = str(getattr(p, "temperature_unit", "") or "")
            short = str(getattr(p, "short_forecast", "") or "")
            wind = str(getattr(p, "wind_speed", "") or "")

            line1 = f"{ts}{SEP}{temp}{unit}".strip()
            sub_parts: list[str] = []
            if short:
                sub_parts.append(short)
            if wind:
                sub_parts.append(f"Wind {wind}")
            line2 = SEP.join(sub_parts)
            line3 = ""

            payload = {
                "title": line1,
                "body": "\n".join([x for x in (line2, line3) if x]).strip(),
            }

            item = QListWidgetItem("\n".join([x for x in (line1, line2, line3) if x]))
            item.setData(Qt.UserRole, payload)
            self._list.addItem(item)

    def _render_alerts(self) -> None:
        alerts = (self._data or {}).get("alerts")
        features = getattr(alerts, "features", []) or []
        if not features:
            self._list.addItem(QListWidgetItem("No active alerts"))
            return

        for a in features:
            severity = str(getattr(a, "severity", "") or "")
            event = str(getattr(a, "event", "") or "")
            headline = str(getattr(a, "headline", "") or "")
            desc = str(getattr(a, "description", "") or "")

            prefix = f"[{severity}]" if severity else ""
            line1 = SEP.join([x for x in (prefix, event) if x]).strip()
            line2 = headline

            payload = {
                "title": line1,
                "body": "\n\n".join([x for x in (headline, desc) if x]).strip(),
            }

            item = QListWidgetItem("\n".join([x for x in (line1, line2) if x]))
            item.setData(Qt.UserRole, payload)
            self._list.addItem(item)
