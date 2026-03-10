import ssl
import re
import urllib.request
import xml.etree.ElementTree as ET
import logging

def handle_news_branch(question, q_lower, response, logger=None, apps=None, geo=None):
    """
    Populate response with a 'news' card. Returns True if branch handled.
    """
    if logger is None:
        logger = logging.getLogger("cortana2")
    logger.debug("handle_news_branch: starting news fetch/parse")

    response["speech"] = "Here are today’s top headlines."
    response["display_markdown"] = "Here are today’s top headlines."

    try:
        FEED_URL = "https://www.windowscentral.com/feeds.xml"
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(FEED_URL, context=ctx, timeout=8) as resp:
            data = resp.read()

        root = ET.fromstring(data)

        def child_text(elem, name):
            for c in elem:
                tag = c.tag
                if tag == name or tag.endswith("}" + name):
                    return (c.text or "").strip()
            return None

        def find_children_local(elem, name):
            out = []
            for c in elem:
                tag = c.tag
                if tag == name or tag.endswith("}" + name):
                    out.append(c)
            return out

        def find_first_local(elem, name):
            for c in elem:
                tag = c.tag
                if tag == name or tag.endswith("}" + name):
                    return c
            return None

        def extract_author(raw):
            if not raw:
                return None
            raw = raw.strip()
            m = re.search(r"\(([^)]+)\)", raw)
            if m:
                return m.group(1).strip()
            return raw

        items = root.findall('.//item')
        articles = []
        for it in items:
            title = child_text(it, "title") or "Untitled"
            link = child_text(it, "link") or ""
            author_raw = child_text(it, "author") or child_text(it, "creator")
            author = extract_author(author_raw)

            cats = []
            for c in find_children_local(it, "category"):
                if c.text and c.text.strip():
                    cats.append(c.text.strip())

            thumb_url = None
            thumb_elem = find_first_local(it, "thumbnail")
            if thumb_elem is not None:
                thumb_url = thumb_elem.attrib.get("url") or thumb_elem.attrib.get("{http://search.yahoo.com/mrss/}url")

            if not thumb_url:
                content_elem = find_first_local(it, "content")
                if content_elem is not None:
                    thumb_url = content_elem.attrib.get("url")
            if not thumb_url:
                encl = find_first_local(it, "enclosure")
                if encl is not None:
                    thumb_url = encl.attrib.get("url")

            articles.append({
                "title": title,
                "url": link,
                "author": author,
                "categories": cats,
                "thumbnail": thumb_url
            })

        if not articles:
            raise ValueError("no articles found in feed")

    except Exception:
        logger.exception("handle_news_branch: failed to fetch/parse feed, falling back to defaults")
        articles = [
            {"title": "An Error Occurred", "url": "https://example.com/ai-news", "author": "Cortana2", "categories": ["Error", "AI", "News"], "thumbnail": None},
            {"title": "We Could Not Get The News", "url": "https://example.com/privacy", "author": "Cortana2", "categories": ["Error", "Privacy", "Update"], "thumbnail": None},
            {"title": "Check The Console", "url": "https://example.com/spacex", "author": "Cortana2", "categories": ["Error", "Console", "Debug"], "thumbnail": None},
            {"title": "And For A User", "url": "https://example.com/spacex", "author": "Cortana2", "categories": ["Error", "User", "Info"], "thumbnail": None},
            {"title": "Try Again Later", "url": "https://example.com/updates", "author": "Cortana2", "categories": ["Error", "Retry", "Updates"], "thumbnail": None}
        ]

    # Easter egg: if prompted with "the goddess of windows", prefer Zac Bowden articles
    if isinstance(q_lower, str) and "the goddess of windows" in q_lower:
        logger.debug("handle_news_branch: easter egg -> filtering for author 'Zac Bowden'")
        filtered = [a for a in articles if a.get("author") and "zac bowden" in a["author"].lower()]
        if filtered:
            articles = filtered

    response["cards"].append({
        "type": "news",
        "articles": articles
    })
    logger.debug("handle_news_branch: appended news card, articles=%d", len(articles))
    return True
