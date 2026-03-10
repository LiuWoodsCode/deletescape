import json, re, html
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

__all__ = ["render_card_html"]

_WEATHER_MAP = {0:"🌪️",1:"🌀",2:"🌀",3:"🌩️",4:"⛈️",5:"🌨️",6:"🌨️",7:"🌨️",8:"🌧️",9:"🌦️",10:"🌧️",11:"🌦️",12:"🌧️",13:"🌨️",14:"🌨️",15:"❄️",16:"❄️",17:"🌨️",18:"🌨️",19:"🌬️",20:"🌫️",21:"🌫️",22:"🌫️",23:"🌬️",24:"🌬️",25:"❄️",26:"☁️",27:"☁️",28:"☁️",29:"🌤️",30:"🌤️",31:"🌙",32:"☀️",33:"🌙",34:"🌤️",35:"🌨️",36:"🔥",37:"⛈️",38:"⛈️",39:"🌦️",40:"🌧️",41:"🌨️",42:"❄️",43:"🌨️",44:"🌡️",45:"🌦️",46:"🌨️",47:"⛈️"}

_HTML_MAX_JSON = 600
_SEARCH_MAX = 6

def _escape(s: Any) -> str:
    if s is None: return ""
    return html.escape(str(s), quote=True)

def _is_webp_url(url: Optional[str]) -> bool:
    if not url: return False
    u = url.lower()
    return bool(re.search(r"\.(webp|svg|heic|heif|avif)(?:$|[?&#])", u))

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
        if re.search(r"thunder|storm|lightning", c): return "⛈️"
        if re.search(r"rain|shower|drizzle", c): return "🌧️"
        if re.search(r"snow|sleet|ice|blizzard", c): return "❄️"
        if re.search(r"fog|mist|haze|smog", c): return "🌫️"
        if re.search(r"wind|breeze|gale", c): return "🌬️"
        if "cloud" in c: return "☁️"
        if re.search(r"clear|sun", c): return "☀️"
    return "🌡️"

def _render_kv(label: str, value: Any) -> str:
    if value is None: return ""
    if isinstance(value, dict) and 'label' in value:
        value = value.get('label')
    return f"<div class='kv'><strong>{_escape(label)}:</strong> {_escape(value)}</div>"

def _render_image(url: Optional[str]) -> str:
    if not url: return ""
    if _is_webp_url(url):
        return f"<div class='img note'>Image format not supported: {_escape(url)}</div>"
    return f"<img src='{_escape(url)}' class='card-img' loading='lazy'>"

def _render_person(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Born", card.get("birth_date")), ("Died", card.get("death_date")), ("Gender", card.get("gender")), ("Birthplace", card.get("birth_place")), ("Wikipedia", card.get("wikipedia"))]:
        parts.append(_render_kv(k, v))
    return "".join(parts)

def _render_film(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Director", card.get("director")), ("Released", card.get("publication_date")), ("Wikipedia", card.get("wikipedia"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_book(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Author", card.get("author")), ("Published", card.get("publication_date")), ("ISBN", card.get("isbn"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_org(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Founded", card.get("inception")), ("HQ", card.get("headquarters")), ("Website", card.get("official_website"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_software(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Developer", card.get("developer")), ("Language", card.get("programming_language")), ("Website", card.get("official_website"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_taxon(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Name", card.get("taxon_name")), ("Rank", card.get("taxon_rank")), ("Parent", card.get("parent_taxon"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_chemical(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Formula", card.get("chemical_formula")), ("CAS", card.get("cas_number"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_place(card: Dict[str, Any]) -> str:
    parts = []
    parts.append(_render_kv("Country", card.get("country")))
    parts.append(_render_kv("Population", card.get("population")))
    coords = card.get("coordinates")
    if isinstance(coords, dict) and coords.get('lat') is not None and coords.get('lon') is not None:
        parts.append(_render_kv("Coords", f"{coords.get('lat')}, {coords.get('lon')}"))
    return "".join(parts)

def _render_event(card: Dict[str, Any]) -> str:
    parts = []
    for k,v in [("Start", card.get("start_time")), ("End", card.get("end_time")), ("Location", card.get("location"))]:
        parts.append(_render_kv(k,v))
    return "".join(parts)

def _render_currentconditions(card: Dict[str, Any]) -> str:
    wx = card.get('forecast') or card.get('current') or card
    condition = next((wx.get(k) for k in ("condition","condition_text","summary","text") if wx.get(k)), None)
    icon_code = next((wx.get(k) for k in ("condition_icon","icon") if wx.get(k) is not None), card.get('condition_icon'))
    temp = next((wx.get(k) for k in ("temperatureCelsius","tempC","temperature","temp") if wx.get(k) is not None), None)
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
    parts = [f"<p class='wx-main'>{_escape(emoji)} {_escape(temp_str)} — {_escape(condition or 'Unknown')}</p>"]
    if feels: parts.append(f"<p>Feels like: {_escape(feels)}</p>")
    if humidity is not None:
        h = str(humidity)
        if not h.endswith('%'):
            try:
                if float(h) >= 0: h += '%'
            except Exception:
                pass
        parts.append(f"<p>Humidity: {_escape(h)}</p>")
    if wind is not None:
        w = str(wind)
        if not re.search(r"(km/h|mph|m/s)$", w):
            try:
                float(w)
                w += " km/h"
            except Exception:
                pass
        parts.append(f"<p>Wind: {_escape(w)}</p>")
    loc = card.get('location')
    if isinstance(loc, dict) and loc.get('lat') is not None and loc.get('lon') is not None:
        parts.append(f"<p>Location: {_escape(loc.get('lat'))}, {_escape(loc.get('lon'))}</p>")
    return "".join(parts)

def _render_search(card: Dict[str, Any]) -> str:
    results = card.get('results') or []
    if not results:
        return "<p>No results.</p>"
    rows = []
    for r in results[:_SEARCH_MAX]:
        title = r.get('title') or r.get('url') or 'Result'
        url = r.get('url')
        snippet = (r.get('snippet') or '')[:160]
        t_html = _escape(title)
        if url:
            t_html = f"<a href='{_escape(url)}' target='_blank'>{t_html}</a>"
        sn_html = f"<div class='snippet'>{_escape(snippet)}</div>" if snippet else ''
        rows.append(f"<li>{t_html}{sn_html}</li>")
    return f"<p>Results: {len(results)} (showing up to {_SEARCH_MAX})</p><ul>{''.join(rows)}</ul>"

def _render_news(card: Dict[str, Any]) -> str:
    articles = card.get('articles') or []
    if not articles:
        return "<p>No articles.</p>"
    rows = []
    for a in articles:
        title = a.get('title') or a.get('url') or 'Article'
        url = a.get('url')
        host = ''
        if url:
            try:
                host = urlparse(url).hostname or ''
            except Exception:
                host = ''
        thumb_html = ''
        thumb = a.get('thumbnail')
        if thumb and not _is_webp_url(thumb):
            thumb_html = f"<img src='{_escape(thumb)}' class='thumb' loading='lazy' style='width:120px;max-height:120px;object-fit:cover;border-radius:8px;'>"
        meta = []
        if host: meta.append(_escape(host))
        if a.get('author'): meta.append(f"by {_escape(a.get('author'))}")
        cats = a.get('categories')
        if cats:
            if isinstance(cats, (list, tuple)):
                cats_str = " • ".join(_escape(c) for c in cats if c)
            else:
                cats_str = _escape(cats)
            if cats_str: meta.append(cats_str)
        meta_html = f"<div class='meta' style='color:#888;font-size:12px;margin:4px 0 0'>{' | '.join(meta)}</div>" if meta else ''
        title_html = _escape(title)
        if url:
            title_html = f"<a href='{_escape(url)}' target='_blank'>{title_html}</a>"
        rows.append(
            "<li class='news-item' style='display:flex;gap:12px;align-items:flex-start;margin:10px 0'>" +
            (f"<div class='thumb-wrap' style='flex:0 0 auto'>{thumb_html}</div>" if thumb_html else "") +
            f"<div class='news-text' style='flex:1;min-width:0'><div class='news-title' style='font-weight:600'>{title_html}</div>{meta_html}</div>" +
            "</li>"
        )
    return f"<p>Articles: {len(articles)}</p><ul class='news-list' style='list-style:none;padding:0;margin:0'>{''.join(rows)}</ul>"

def _is_bad_image_url(url: Optional[str]) -> bool:
    if not url:
        return False
    u = url.lower()
    bad = bool(re.search(r"\.(webp|svg|heic|heif|avif)(?:$|[?&#])", u))
    if bad:
        print("Rejecting image URL with unsupported format: %s", url)
    return bad

def render_card_html(card: Dict[str, Any]) -> str:
    ctype = card.get('type') or '<unknown>'
    label = card.get('label') or ''
    image_html = _render_image(card.get('image'))
    body_html = ''
    if ctype == 'blank': return (
        "<div class='card'>"
        "</div>"
    )
    elif ctype == 'person': body_html = _render_person(card)
    elif ctype == 'film': body_html = _render_film(card)
    elif ctype == 'book': body_html = _render_book(card)
    elif ctype == 'organization': body_html = _render_org(card)
    elif ctype == 'software': body_html = _render_software(card)
    elif ctype == 'taxon': body_html = _render_taxon(card)
    elif ctype == 'chemical': body_html = _render_chemical(card)
    elif ctype == 'place': body_html = _render_place(card)
    elif ctype == 'event': body_html = _render_event(card)
    elif ctype == 'currentconditions': body_html = _render_currentconditions(card)
    elif ctype == 'search': body_html = _render_search(card)
    elif ctype == 'news': body_html = _render_news(card)
    else:
        try:
            s = json.dumps(card, ensure_ascii=False)
            if len(s) > _HTML_MAX_JSON: s = s[:_HTML_MAX_JSON] + '...'
            body_html = f"<pre>{_escape(s)}</pre>"
        except Exception:
            body_html = "<p>(could not serialize card)</p>"
    desc = card.get('description')
    desc_html = f"<div class='desc'>{_escape(desc)}</div>" if desc else ''
    # New structure: keep title as-is, then a .card-body flex container with the image on the left
    # and a .card-content container on the right that stacks description + body vertically.
    return (
        "<div class='card'>"
        f"<h2>{_escape(ctype)}: {_escape(label)}</h2>"
        "<div class='card-body'>"
        f"{image_html}"
        f"<div class='card-content'>{desc_html}{body_html}</div>"
        "</div>"
        "</div>"
    )

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
        html_block = _render_search(card)
    elif ctype == "news":
        html_block = _render_news(card)
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