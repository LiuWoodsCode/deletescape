import json
import html
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from datetime import datetime

import logging

logger = logging.getLogger("assistant.frontend.card_renderer")

__all__ = ["render_card_widget_data"]

_WEATHER_MAP = {
    0: "🌪️", 1: "🌀", 2: "🌀", 3: "🌩️", 4: "⛈️", 5: "🌨️", 6: "🌨️", 7: "🌨️",
    8: "🌧️", 9: "🌦️", 10: "🌧️", 11: "🌦️", 12: "🌧️", 13: "🌨️", 14: "🌨️",
    15: "❄️", 16: "❄️", 17: "🌨️", 18: "🌨️", 19: "🌬️", 20: "🌫️", 21: "🌫️",
    22: "🌫️", 23: "🌬️", 24: "🌬️", 25: "❄️", 26: "☁️", 27: "☁️", 28: "☁️",
    29: "🌤️", 30: "🌤️", 31: "🌙", 32: "☀️", 33: "🌙", 34: "🌤️", 35: "🌨️",
    36: "🔥", 37: "⛈️", 38: "⛈️", 39: "🌦️", 40: "🌧️", 41: "🌨️", 42: "❄️",
    43: "🌨️", 44: "🌡️", 45: "🌦️", 46: "🌨️", 47: "⛈️"
}

_HTML_MAX_JSON = 600
_SEARCH_MAX = 6


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def _is_bad_image_url(url: Optional[str]) -> bool:
    if not url:
        return False
    u = url.lower()
    bad = bool(re.search(r"\.(webp|svg|heic|heif|avif)(?:$|[?&#])", u))
    if bad:
        logger.debug("Rejecting image URL with unsupported format: %s", url)
    return bad


def _get_weather_emoji(icon_code: Optional[int], condition: Optional[str]) -> str:
    if icon_code is not None:
        try:
            ic = int(icon_code)
            if ic in _WEATHER_MAP:
                return _WEATHER_MAP[ic]
        except Exception:
            pass

    if condition:
        c = condition.lower()
        if re.search(r"thunder|storm|lightning", c):
            return "⛈️"
        if re.search(r"rain|shower|drizzle", c):
            return "🌧️"
        if re.search(r"snow|sleet|ice|blizzard", c):
            return "❄️"
        if re.search(r"fog|mist|haze|smog", c):
            return "🌫️"
        if re.search(r"wind|breeze|gale", c):
            return "🌬️"
        if "cloud" in c:
            return "☁️"
        if re.search(r"clear|sun", c):
            return "☀️"

    return "🌡️"


def _line(label: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    formatted_value = value
    if label in ["Born", "Died", "Released", "Published", "Founded", "Start", "End"]:
        formatted_value = _format_date(value)
    if isinstance(value, dict) and "label" in value:
        formatted_value = value.get("label")
    return f"{label}: {formatted_value}"


def _format_date(date_str: Any) -> str:
    if not isinstance(date_str, str):
        return str(date_str)
    try:
        # Handle Wikidata date format: e.g., +1970-01-01T00:00:00Z or -0043-01-01T00:00:00Z
        if date_str.startswith('+') or date_str.startswith('-'):
            sign = date_str[0]
            rest = date_str[1:]
            dt = datetime.fromisoformat(rest.replace('Z', '+00:00'))
            # For BCE dates, we can still format them, though year might be negative
        else:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%b %d, %Y (%I:%M %p)")
    except Exception:
        return date_str


def _render_person(card: Dict[str, Any]) -> List[str]:
    logger.debug("Rendering person card for label=%s", card.get("label"))
    return [
        v for v in [
            _line("Born", card.get("birth_date")),
            _line("Died", card.get("death_date")),
            _line("Gender", card.get("gender")),
            _line("Birthplace", card.get("birth_place")),
            _line("Wikipedia", card.get("wikipedia")),
        ] if v
    ]


def _render_film(card: Dict[str, Any]) -> List[str]:
    logger.debug("Rendering film card with director=%s", card.get("director"))
    return [
        v for v in [
            _line("Director", card.get("director")),
            _line("Released", card.get("publication_date")),
            _line("Wikipedia", card.get("wikipedia")),
        ] if v
    ]


def _render_book(card: Dict[str, Any]) -> List[str]:
    logger.debug("Rendering book card for author=%s", card.get("author"))
    return [
        v for v in [
            _line("Author", card.get("author")),
            _line("Published", card.get("publication_date")),
            _line("ISBN", card.get("isbn")),
        ] if v
    ]


def _render_org(card: Dict[str, Any]) -> List[str]:
    logger.debug("Rendering organization card with HQ=%s", card.get("headquarters"))
    return [
        v for v in [
            _line("Founded", card.get("inception")),
            _line("HQ", card.get("headquarters")),
            _line("Website", card.get("official_website")),
        ] if v
    ]


def _render_software(card: Dict[str, Any]) -> List[str]:
    return [
        v for v in [
            _line("Developer", card.get("developer")),
            _line("Language", card.get("programming_language")),
            _line("Website", card.get("official_website")),
        ] if v
    ]


def _render_taxon(card: Dict[str, Any]) -> List[str]:
    return [
        v for v in [
            _line("Name", card.get("taxon_name")),
            _line("Rank", card.get("taxon_rank")),
            _line("Parent", card.get("parent_taxon")),
        ] if v
    ]


def _render_chemical(card: Dict[str, Any]) -> List[str]:
    return [
        v for v in [
            _line("Formula", card.get("chemical_formula")),
            _line("CAS", card.get("cas_number")),
        ] if v
    ]


def _render_place(card: Dict[str, Any]) -> List[str]:
    parts = []
    for entry in [
        _line("Country", card.get("country")),
        _line("Population", card.get("population")),
    ]:
        if entry:
            parts.append(entry)

    coords = card.get("coordinates")
    if isinstance(coords, dict) and coords.get("lat") is not None and coords.get("lon") is not None:
        parts.append(f"Coords: {coords.get('lat')}, {coords.get('lon')}")
    return parts


def _render_event(card: Dict[str, Any]) -> List[str]:
    return [
        v for v in [
            _line("Start", card.get("start_time")),
            _line("End", card.get("end_time")),
            _line("Location", card.get("location")),
        ] if v
    ]


def _render_currentconditions(card: Dict[str, Any]) -> List[str]:
    wx = card.get("forecast") or card.get("current") or card
    condition = next((wx.get(k) for k in ("condition", "condition_text", "summary", "text") if wx.get(k)), None)
    icon_code = next((wx.get(k) for k in ("condition_icon", "icon") if wx.get(k) is not None), card.get("condition_icon"))
    temp = next((wx.get(k) for k in ("temperatureCelsius", "tempC", "temperature", "temp") if wx.get(k) is not None), None)
    feels = wx.get("feels_like") or wx.get("apparent_temperature")
    humidity = wx.get("humidity")
    wind = wx.get("wind") or wx.get("wind_speed")
    emoji = _get_weather_emoji(icon_code, condition)

    if temp is not None:
        temp_str = str(temp)
        if not re.search(r"(°|C|F)$", temp_str):
            temp_str += "°C"
    else:
        temp_str = "—"

    parts = [f"{emoji} {temp_str} — {condition or 'Unknown'}"]

    if feels:
        parts.append(f"Feels like: {feels}")

    if humidity is not None:
        h = str(humidity)
        if not h.endswith("%"):
            try:
                if float(h) >= 0:
                    h += "%"
            except Exception:
                pass
        parts.append(f"Humidity: {h}")

    if wind is not None:
        w = str(wind)
        if not re.search(r"(km/h|mph|m/s)$", w):
            try:
                float(w)
                w += " km/h"
            except Exception:
                pass
        parts.append(f"Wind: {w}")

    loc = card.get("location")
    if isinstance(loc, dict) and loc.get("lat") is not None and loc.get("lon") is not None:
        parts.append(f"Location: {loc.get('lat')}, {loc.get('lon')}")

    return parts


def _render_search_html(card: Dict[str, Any]) -> str:
    results = card.get("results") or []
    if not results:
        return "<p>No results.</p>"

    rows = []
    for r in results[:_SEARCH_MAX]:
        title = r.get("title") or r.get("url") or "Result"
        url = r.get("url")
        snippet = (r.get("snippet") or "")[:160]

        title_html = _escape(title)
        if url:
            title_html = f"<a href='{_escape(url)}'>{title_html}</a>"

        snippet_html = f"<div style='color:#c7d0e6; margin-top:4px;'>{_escape(snippet)}</div>" if snippet else ""
        rows.append(f"<li style='margin-bottom:8px;'>{title_html}{snippet_html}</li>")

    return f"<p>Results: {len(results)} (showing up to {_SEARCH_MAX})</p><ul>{''.join(rows)}</ul>"


def _render_news_html(card: Dict[str, Any]) -> str:
    articles = card.get("articles") or []
    if not articles:
        return "<p>No articles.</p>"

    rows = []
    for a in articles:
        title = a.get("title") or a.get("url") or "Article"
        url = a.get("url")
        host = ""
        if url:
            try:
                host = urlparse(url).hostname or ""
            except Exception:
                host = ""

        meta = []
        if host:
            meta.append(_escape(host))
        if a.get("author"):
            meta.append(f"by {_escape(a.get('author'))}")
        cats = a.get("categories")
        if cats:
            if isinstance(cats, (list, tuple)):
                cats_str = " • ".join(_escape(c) for c in cats if c)
            else:
                cats_str = _escape(cats)
            if cats_str:
                meta.append(cats_str)

        meta_html = f"<div style='color:#9aa4c2; font-size:12px; margin-top:4px;'>{' | '.join(meta)}</div>" if meta else ""
        title_html = _escape(title)
        if url:
            title_html = f"<a href='{_escape(url)}'>{title_html}</a>"

        rows.append(f"<li style='margin-bottom:10px;'><div><strong>{title_html}</strong></div>{meta_html}</li>")

    return f"<p>Articles: {len(articles)}</p><ul>{''.join(rows)}</ul>"


def render_card_widget_data(card: Dict[str, Any]) -> Dict[str, Any]:
    ctype = card.get("type") or "<unknown>"
    label = card.get("label") or ""
    description = card.get("description") or ""
    image = card.get("image")

    if _is_bad_image_url(image):
        image = None

    title = f"{label}"
    lines: List[str] = []
    html_block = ""

    if ctype == "person":
        lines = _render_person(card)
    elif ctype == "film":
        lines = _render_film(card)
    elif ctype == "book":
        lines = _render_book(card)
    elif ctype == "organization":
        lines = _render_org(card)
    elif ctype == "software":
        lines = _render_software(card)
    elif ctype == "taxon":
        lines = _render_taxon(card)
    elif ctype == "chemical":
        lines = _render_chemical(card)
    elif ctype == "place":
        lines = _render_place(card)
    elif ctype == "event":
        lines = _render_event(card)
    elif ctype == "currentconditions":
        lines = _render_currentconditions(card)
    elif ctype == "search":
        html_block = _render_search_html(card)
    elif ctype == "news":
        html_block = _render_news_html(card)
    else:
        try:
            s = json.dumps(card, ensure_ascii=False, indent=2)
            if len(s) > _HTML_MAX_JSON:
                s = s[:_HTML_MAX_JSON] + "..."
            html_block = f"<pre>{_escape(s)}</pre>"
        except Exception:
            html_block = "<p>(could not serialize card)</p>"

    return {
        "title": title,
        "description": description,
        "image": image,
        "lines": lines,
        "html_block": html_block,
    }