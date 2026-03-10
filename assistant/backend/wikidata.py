import logging
import os
from typing import List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


logger = logging.getLogger("cortana2.wikidata")

# --- Wikidata / Wikimedia endpoints ---
USE_LOCAL_WIKIDATA = os.getenv("USE_LOCAL_WIKIDATA", "0") == "1"
# New: merge mode (0=off, 1=prefer local always, 2=prefer real with local fallback)
try:
    MERGE_WIKIDATA = int(os.getenv("MERGE_WIKIDATA", "0") or "0")
except ValueError:
    MERGE_WIKIDATA = 0

if USE_LOCAL_WIKIDATA:
    WIKIDATA_API = "http://localhost:3192/w/api.php"
    WIKIDATA_ENTITY_JSON = "http://localhost:3192/wiki/Special:EntityData/{}.json"
    WIKIMEDIA_FILE_URL = "http://localhost:3192/wiki/Special:FilePath/{}"
else:
    WIKIDATA_API = "https://www.wikidata.org/w/api.php"
    WIKIDATA_ENTITY_JSON = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
    WIKIMEDIA_FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{}"
# Added: Commons API to resolve real image URLs
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# New: fixed endpoint definitions for both real and local, used when merging
REAL_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
REAL_WIKIDATA_ENTITY_JSON = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
REAL_WIKIMEDIA_FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{}"
REAL_COMMONS_API = "https://commons.wikimedia.org/w/api.php"

LOCAL_WIKIDATA_API = "http://localhost:3192/w/api.php"
LOCAL_WIKIDATA_ENTITY_JSON = "http://localhost:3192/wiki/Special:EntityData/{}.json"
LOCAL_WIKIMEDIA_FILE_URL = "http://localhost:3192/wiki/Special:FilePath/{}"
LOCAL_COMMONS_API = "http://localhost:3192/w/api.php"


# Add robust session with User-Agent and retries to avoid 403s / transient failures
WIKIDATA_USER_AGENT = os.getenv(
    "WIKIDATA_USER_AGENT",
    "Cortana2/0.4 (https://example.com; contact@example.com)",
)
_session = requests.Session()
_session.headers.update({"User-Agent": WIKIDATA_USER_AGENT, "Accept": "application/json"})
# Slightly more aggressive retry, but keep overall latency reasonable
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# --------- Lightweight in-memory caches to cut repeated network calls ---------
# NOTE: process-local best-effort caches; no eviction policy needed for typical usage sizes.
_SEARCH_CACHE: Dict[Tuple[str, str], Dict] = {}
_ENTITY_CACHE: Dict[Tuple[str, str], Dict] = {}
_LABELS_CACHE: Dict[Tuple[str, Tuple[str, ...]], Dict[str, str]] = {}
_IMAGE_CACHE: Dict[Tuple[str, str], Optional[str]] = {}


# New: helpers to choose endpoints per source and try order based on merge mode
def _endpoints_for(source: str) -> Dict[str, str]:
    if source == "local":
        return {
            "api": LOCAL_WIKIDATA_API,
            "entity_json": LOCAL_WIKIDATA_ENTITY_JSON,
            "file_url": LOCAL_WIKIMEDIA_FILE_URL,
            "commons_api": LOCAL_COMMONS_API,
        }
    return {
        "api": REAL_WIKIDATA_API,
        "entity_json": REAL_WIKIDATA_ENTITY_JSON,
        "file_url": REAL_WIKIMEDIA_FILE_URL,
        "commons_api": REAL_COMMONS_API,
    }


def _try_order() -> List[str]:
    if not USE_LOCAL_WIKIDATA:
        return ["real"]
    if MERGE_WIKIDATA == 1:
        # Prefer local, but fall back to real if local does not have the entry
        return ["local", "real"]
    if MERGE_WIKIDATA == 2:
        # Prefer real, fall back to local only if real cannot find the entry
        return ["real", "local"]
    return ["local"]


def wikidata_search_entity(name: str) -> Optional[Dict]:
    logger.debug("wikidata_search_entity: query=%r", name)
    # Fast-path cache: key by (normalized_name, source)
    norm = name.strip().lower()
    for source in _try_order():
        cache_key = (source, norm)
        if cache_key in _SEARCH_CACHE:
            logger.debug("wikidata_search_entity[%s]: cache hit for %r", source, norm)
            return _SEARCH_CACHE[cache_key]

    for source in _try_order():
        try:
            ep = _endpoints_for(source)
            params = {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "format": "json",
                "limit": 1,
            }
            r = _session.get(ep["api"], params=params, timeout=3)
            logger.debug(
                "wikidata_search_entity[%s]: request url=%s params=%s status=%s",
                source, r.url, params, r.status_code,
            )
            r.raise_for_status()
            data = r.json()
            logger.debug("wikidata_search_entity[%s]: response_keys=%s", source, list(data.keys()))
            if data.get("search"):
                res = data["search"][0]
                res["_source"] = source  # mark source for downstream logic
                logger.debug(
                    "wikidata_search_entity[%s]: found id=%s label=%s", source, res.get("id"), res.get("label")
                )
                _SEARCH_CACHE[(source, norm)] = res
                return res
        except Exception as e:
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 403:
                logger.error(
                    "wikidata_search_entity[%s]: received 403 Forbidden. "
                    "Ensure a valid User-Agent is set via WIKIDATA_USER_AGENT env var.",
                    source,
                )
            logger.exception("wikidata_search_entity[%s]: exception while searching %r: %s", source, name, e)
    return None


def wikidata_fetch_entity(qid: str) -> Optional[Dict]:
    logger.debug("wikidata_fetch_entity: qid=%r", qid)
    # Cache by (source, qid) to avoid refetching entities within a run
    for source in _try_order():
        cache_key = (source, qid)
        if cache_key in _ENTITY_CACHE:
            logger.debug("wikidata_fetch_entity[%s]: cache hit for %s", source, qid)
            return _ENTITY_CACHE[cache_key]

    for source in _try_order():
        try:
            ep = _endpoints_for(source)
            url = ep["entity_json"].format(qid)
            r = _session.get(url, timeout=4)
            logger.debug("wikidata_fetch_entity[%s]: fetched url=%s status=%s", source, r.url, r.status_code)
            r.raise_for_status()
            data = r.json()
            ent = data.get("entities", {}).get(qid)
            logger.debug("wikidata_fetch_entity[%s]: entity_present=%s", source, bool(ent))
            if ent:
                ent["_source"] = source  # mark source for downstream logic
                _ENTITY_CACHE[(source, qid)] = ent
                return ent
        except Exception as e:
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 403:
                logger.error(
                    "wikidata_fetch_entity[%s]: received 403 Forbidden for qid=%s. "
                    "Set a descriptive WIKIDATA_USER_AGENT to avoid being blocked.",
                    source, qid,
                )
            logger.exception("wikidata_fetch_entity[%s]: exception fetching %s: %s", source, qid, e)
    return None


def fetch_labels_for_qids(qids: List[str], source: Optional[str] = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not qids:
        return out
    # Choose endpoint based on provided source (if any), otherwise keep legacy behavior
    ep_api = _endpoints_for(source)["api"] if source in ("real", "local") else WIKIDATA_API

    # Deduplicate while preserving order
    seen = set()
    uniq_qids: List[str] = []
    for q in qids:
        if q and q not in seen:
            seen.add(q)
            uniq_qids.append(q)

    # Try cache first for the full tuple of requested ids
    cache_key = (source or "auto", tuple(uniq_qids))
    if cache_key in _LABELS_CACHE:
        logger.debug("fetch_labels_for_qids[%s]: cache hit for %d qids", source or "auto", len(uniq_qids))
        return dict(_LABELS_CACHE[cache_key])

    # Wikidata wbgetentities max ids per request is 50 for non-bot keys
    max_batch = max(1, min(40, int(os.getenv("WIKIDATA_LABELS_BATCH", "40") or 40)))
    logger.debug(
        "fetch_labels_for_qids[%s]: qids=%s batches=%d batch_size=%d",
        source or ("legacy" if USE_LOCAL_WIKIDATA else "real"),
        uniq_qids,
        (len(uniq_qids) + max_batch - 1) // max_batch,
        max_batch,
    )

    idx = 0
    while idx < len(uniq_qids):
        batch = uniq_qids[idx: idx + max_batch]
        idx += max_batch
        try:
            params = {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels",
                "languages": "en",
                "format": "json",
            }
            r = _session.get(ep_api, params=params, timeout=4)
            logger.debug(
                "fetch_labels_for_qids[%s]: request url=%s status=%s batch_count=%d",
                source or "auto", r.url, r.status_code, len(batch)
            )
            r.raise_for_status()
            j = r.json()
            if j.get("error"):
                logger.warning(
                    "fetch_labels_for_qids[%s]: api error code=%s info=%s for batch size=%d",
                    source or "auto",
                    j["error"].get("code"),
                    j["error"].get("info"),
                    len(batch),
                )
                continue
            data = j.get("entities", {})
            for q, ent in data.items():
                label = ((ent.get("labels") or {}).get("en") or {}).get("value")
                if label:
                    out[q] = label
        except Exception as e:
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 403:
                logger.error(
                    "fetch_labels_for_qids[%s]: received 403 Forbidden when resolving qids=%s. "
                    "Set WIKIDATA_USER_AGENT if necessary.",
                    source or "auto", batch,
                )
            logger.exception("fetch_labels_for_qids[%s]: exception for batch=%s: %s", source or "auto", batch, e)

    logger.debug("fetch_labels_for_qids[%s]: resolved_labels_count=%d", source or "auto", len(out))
    _LABELS_CACHE[cache_key] = dict(out)
    return out


def claim_value(claim):
    # extract sensible value from a claim snak (best-effort)
    snak = claim.get("mainsnak", {})
    dv = snak.get("datavalue", {})
    if not dv:
        return None
    val = dv.get("value")
    dtype = dv.get("type")
    logger.debug("claim_value: type=%s value_preview=%r", dtype, (str(val)[:200] if val is not None else None))
    return val


# Added: Resolve Commons Special:FilePath to the actual upload URL using the Commons API, with redirect fallback
# Changed: now source-aware; only correct URLs for source="real". For "local", return local Special:FilePath as-is.
def resolve_commons_image_url(filename: str, source: Optional[str] = None) -> Optional[str]:
    # Simple cache to avoid re-resolving hot images
    effective_source = source if source in ("real", "local") else ("local" if USE_LOCAL_WIKIDATA else "real")
    cache_key = (effective_source, filename)
    if cache_key in _IMAGE_CACHE:
        logger.debug("resolve_commons_image_url[%s]: cache hit for %r", effective_source, filename)
        return _IMAGE_CACHE[cache_key]

    # Determine source context
    ep = _endpoints_for(effective_source)
    logger.debug("resolve_commons_image_url[%s]: filename=%r", effective_source, filename)

    if effective_source == "local":
        # Do not try to resolve; return local Special:FilePath directly
        url = ep["file_url"].format(requests.utils.requote_uri(filename))
        _IMAGE_CACHE[cache_key] = url
        return url

    # Try Commons API first (original file URL)
    try:
        params = {
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }
        r = _session.get(_endpoints_for("real")["commons_api"], params=params, timeout=4)
        logger.debug("resolve_commons_image_url[real]: api url=%s status=%s", r.url, r.status_code)
        r.raise_for_status()
        data = r.json()
        pages = (data.get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            ii = page.get("imageinfo")
            if ii and isinstance(ii, list) and ii and ii[0].get("url"):
                url = ii[0]["url"]
                logger.debug("resolve_commons_image_url[real]: direct_url=%s", url)
                _IMAGE_CACHE[cache_key] = url
                return url
    except Exception as e:
        logger.exception("resolve_commons_image_url[real]: api resolution failed for %r: %s", filename, e)

    # Fallback: follow redirects from Special:FilePath via HEAD/GET without downloading body
    try:
        file_path_url = _endpoints_for("real")["file_url"].format(requests.utils.requote_uri(filename))
        hr = _session.head(file_path_url, allow_redirects=True, timeout=4)
        logger.debug("resolve_commons_image_url[real]: HEAD resolved to %s status=%s", hr.url, hr.status_code)
        if getattr(hr, "ok", False) and hr.url and "Special:FilePath" not in hr.url:
            _IMAGE_CACHE[cache_key] = hr.url
            return hr.url
        gr = _session.get(file_path_url, allow_redirects=True, timeout=4, stream=True)
        final_url = gr.url
        gr.close()
        if getattr(gr, "ok", False) and final_url and "Special:FilePath" not in final_url:
            _IMAGE_CACHE[cache_key] = final_url
            return final_url
    except Exception as e:
        logger.exception("resolve_commons_image_url[real]: redirect resolution failed for %r: %s", filename, e)

    # Last resort: return the Special:FilePath URL
    url = _endpoints_for("real")["file_url"].format(requests.utils.requote_uri(filename))
    _IMAGE_CACHE[cache_key] = url
    return url


def build_wikidata_card(entity: Dict) -> Dict:
    qid = entity.get("id")
    # Determine entity source context
    source = entity.get("_source") or ("local" if USE_LOCAL_WIKIDATA else "real")
    logger.debug("build_wikidata_card: building card for %s (source=%s)", qid, source)
    labels = entity.get("labels", {})
    label_en = labels.get("en", {}).get("value") if labels else None
    desc_en = entity.get("descriptions", {}).get("en", {}).get("value") if entity.get("descriptions") else None
    aliases = [a.get("value") for a in entity.get("aliases", {}).get("en", [])] if entity.get("aliases") else []
    claims = entity.get("claims", {}) or {}

    # collect referenced QIDs (for instance_of, places, authors, etc.)
    # Use an ordered list so we can prioritize instance_of (P31) entries when fetching labels.
    ref_qids: List[str] = []
    for p, claim_list in claims.items():
        for c in claim_list:
            v = claim_value(c)
            if isinstance(v, dict) and v.get("id"):
                if v["id"] not in ref_qids:
                    ref_qids.append(v["id"])

    # ensure instance_of ids (P31) are prioritized in label resolution so classifications like "human" will be found
    instance_of_ids: List[str] = []
    for c in claims.get("P31", []):  # instance of
        v = claim_value(c)
        if isinstance(v, dict) and v.get("id"):
            iid = v["id"]
            instance_of_ids.append(iid)
            # move instance_of id to front of the list if present, otherwise insert
            if iid in ref_qids:
                ref_qids.remove(iid)
            ref_qids.insert(0, iid)

    # fetch labels for referenced QIDs, prioritizing instance_of IDs; increase limit to include more refs
    ref_labels = fetch_labels_for_qids(ref_qids[:200], source=source)
    logger.debug(
        "build_wikidata_card: ref_qids_count=%d ref_labels_count=%d", len(ref_qids), len(ref_labels)
    )

    # helper getters
    def first_prop_value(pid):
        lst = claims.get(pid)
        if not lst:
            return None
        v = claim_value(lst[0])
        if isinstance(v, dict) and v.get("id"):
            return {"id": v["id"], "label": ref_labels.get(v["id"]) }
        return v

    # common fields
    instance_labels = [ref_labels.get(q) or q for q in instance_of_ids]

    coords = None
    if claims.get("P625"):
        v = claim_value(claims["P625"][0])
        if isinstance(v, dict):
            coords = {"lat": v.get("latitude"), "lon": v.get("longitude")}

    image_url = None
    if claims.get("P18"):
        fname = claim_value(claims["P18"][0])
        if isinstance(fname, str):
            # Changed: resolve only for real responses; for local return Special:FilePath directly
            image_url = resolve_commons_image_url(fname, source=source)

    # person-specific
    birth = None
    death = None
    if claims.get("P569"):
        t = claim_value(claims["P569"][0])
        birth = (t.get("time") if isinstance(t, dict) else t)
    if claims.get("P570"):
        t = claim_value(claims["P570"][0])
        death = (t.get("time") if isinstance(t, dict) else t)

    # other common props
    official_website = None
    if claims.get("P856"):
        official_website = claim_value(claims["P856"][0])

    # sitelinks (e.g., enwiki)
    sitelinks = {}
    for k, v in (entity.get("sitelinks") or {}).items():
        sitelinks[k] = v.get("url") or v.get("title")

    # properties simplified map (first value per property)
    simple_props = {}
    for pid, lst in claims.items():
        v = claim_value(lst[0])
        if isinstance(v, dict) and v.get("id"):
            simple_props[pid] = {
                "id": v["id"],
                "label": ref_labels.get(v["id"]),
            }
        else:
            simple_props[pid] = v

    # determine card type heuristically from instance_of labels
    inst_text = " ".join([str(x).lower() for x in instance_labels if x])
    card = {
        "type": "wikidata",
        "id": qid,
        "label": label_en,
        "description": desc_en,
        "aliases": aliases,
        "sitelinks": sitelinks,
        "properties": simple_props,
        "coordinates": coords,
        "image": image_url,
        "instance_of": instance_labels,
    }

    # specialized cards
    if "human" in inst_text or "person" in inst_text or "human being" in inst_text:
        card["type"] = "person"
        card.update(
            {
                "birth_date": birth,
                "death_date": death,
                "gender": first_prop_value("P21"),
                "birth_place": first_prop_value("P19"),
                "image": image_url,
                "wikipedia": sitelinks.get("enwiki"),
            }
        )
        logger.debug("build_wikidata_card: classified as person for %s", qid)
    elif "film" in inst_text or "motion picture" in inst_text:
        card["type"] = "film"
        card.update(
            {
                "director": first_prop_value("P57"),
                "cast": [
                    claim_value(c).get("id") if isinstance(claim_value(c), dict) else claim_value(c)
                    for c in claims.get("P161", [])
                ],
                "publication_date": first_prop_value("P577"),
                "image": image_url,
                "wikipedia": sitelinks.get("enwiki"),
            }
        )
        logger.debug("build_wikidata_card: classified as film for %s", qid)
    elif "book" in inst_text or "written work" in inst_text:
        card["type"] = "book"
        card.update(
            {
                "author": first_prop_value("P50"),
                "publication_date": first_prop_value("P577"),
                "isbn": first_prop_value("P212") or first_prop_value("P957"),
                "wikipedia": sitelinks.get("enwiki"),
            }
        )
        logger.debug("build_wikidata_card: classified as book for %s", qid)
    elif "taxon" in inst_text or "species" in inst_text or "biological taxon" in inst_text:
        card["type"] = "taxon"
        card.update(
            {
                "taxon_name": first_prop_value("P225"),
                "taxon_rank": first_prop_value("P105"),
                "parent_taxon": first_prop_value("P171"),
                "image": image_url,
                "wikipedia": sitelinks.get("enwiki"),
            }
        )
        logger.debug("build_wikidata_card: classified as taxon for %s", qid)
    elif "software" in inst_text or "computer program" in inst_text:
        card["type"] = "software"
        card.update(
            {
                "developer": first_prop_value("P178"),
                "programming_language": first_prop_value("P277"),
                "official_website": official_website,
                "image": image_url,
            }
        )
        logger.debug("build_wikidata_card: classified as software for %s", qid)
    elif "organization" in inst_text or "company" in inst_text:
        card["type"] = "organization"
        card.update(
            {
                "inception": first_prop_value("P571"),
                "headquarters": first_prop_value("P159"),
                "official_website": official_website,
                "image": image_url,
            }
        )
        logger.debug("build_wikidata_card: classified as organization for %s", qid)
    elif "chemical compound" in inst_text or "chemical" in inst_text or "molecule" in inst_text:
        card["type"] = "chemical"
        card.update(
            {
                "chemical_formula": first_prop_value("P274"),
                "cas_number": first_prop_value("P231"),
                "image": image_url,
            }
        )
        logger.debug("build_wikidata_card: classified as chemical for %s", qid)
    elif "event" in inst_text:
        card["type"] = "event"
        card.update(
            {
                "start_time": first_prop_value("P580"),
                "end_time": first_prop_value("P582"),
                "location": first_prop_value("P276") or first_prop_value("P740"),
            }
        )
        logger.debug("build_wikidata_card: classified as event for %s", qid)
    elif "place" in inst_text or "human settlement" in inst_text or "geographical object" in inst_text:
        card["type"] = "place"
        card.update(
            {
                "population": first_prop_value("P1082"),
                "country": first_prop_value("P17"),
                "coordinates": coords,
                "image": image_url,
            }
        )
        logger.debug("build_wikidata_card: classified as place for %s", qid)

    logger.debug(
        "build_wikidata_card: finished card for %s type=%s properties=%d",
        qid,
        card.get("type"),
        len(simple_props),
    )
    # fallback keeps 'wikidata' card with properties already attached
    return card


__all__ = [
    "wikidata_search_entity",
    "wikidata_fetch_entity",
    "build_wikidata_card",
    "fetch_labels_for_qids",
    "claim_value",
]
