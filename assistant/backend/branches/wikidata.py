import re
import time
from typing import Optional, Dict, Any

# import the existing wikidata helper functions from the parent package
from wikidata import wikidata_search_entity, wikidata_fetch_entity, build_wikidata_card

def handle_wikidata_branch(question: str, q_lower: str, response: Dict[str, Any], logger, apps: Optional[list]=None, geo: Optional[dict]=None, start_t: Optional[float]=None) -> bool:
    """
    Attempt to match and handle Wikidata/entity lookups.
    Returns True if this branch handled the request (response is populated).
    """
    if start_t is None:
        start_t = time.time()
    logger.debug("handle_wikidata_branch: attempting wikidata/entity patterns")
    m = re.search(r"wikidata[:\s]+(.+)$", question, re.I)
    if not m:
        # nlp regex for this branch
        m = re.search(r"^(?:who is|what is|tell me about|lookup|look up|find)\s+(.+)$", question.strip(), re.I)
    if not m:
        return False

    entity_query = m.group(1).strip().strip(" ?.")
    logger.debug("handle_wikidata_branch: entity_query=%r", entity_query)
    if not entity_query:
        return False

    # First attempt: search with the original entity_query
    sd = wikidata_search_entity(entity_query)
    logger.debug("handle_wikidata_branch: wikidata_search_entity returned %s (original query)", bool(sd))

    # If nothing found, and the query starts with a leading article, retry without it
    # For example: 
    # "What is the Weather Channel" is valid (the channel is called "The Weather Channel")
    # but "Who is the Lena Raine" needs to have "the" removed or else we would not find the result
    if not sd:
        m_article = re.match(r"^(?:the|a)\s+(.+)$", entity_query, re.I)
        if m_article:
            stripped_query = m_article.group(1).strip()
            if stripped_query:
                logger.debug(
                    "handle_wikidata_branch: retrying wikidata_search_entity without leading article: %r",
                    stripped_query,
                )
                sd = wikidata_search_entity(stripped_query)
                logger.debug(
                    "handle_wikidata_branch: wikidata_search_entity returned %s (stripped query)",
                    bool(sd),
                )

    if sd:
        qid = sd.get("id")
        ent = wikidata_fetch_entity(qid)
        speech_text = ent.get("speechText") if ent and isinstance(ent, dict) else None
        if speech_text:
            response["speech"] = speech_text

        logger.debug("handle_wikidata_branch: wikidata_fetch_entity returned %s for qid=%s", bool(ent), qid)
        if ent:
            card = build_wikidata_card(ent)
            response["cards"].append(card)
            lbl = card.get("label") or qid
            desc = card.get("description") or ""
            if not response.get("speech"):
                if desc:
                    # this is often gramatically incorrect
                    response["speech"] = f"{lbl} is {desc}."
                else:
                    response["speech"] = f"Here’s what I found about {lbl}."
            response["display_markdown"] = f"Here’s what I found about {lbl}."
            logger.debug("handle_wikidata_branch: returning wikidata card for %s elapsed=%.3fs", qid, time.time()-start_t)
            return True

    # not found / server error case
    # or wikidata is blocked
    # or this is a post WMF world
    # or it's just server problems
    response["speech"] = f"I couldn't find an entity for '{entity_query}' on Wikidata."
    response["display_markdown"] = response["speech"]
    logger.debug("handle_wikidata_branch: wikidata not found for %r elapsed=%.3fs", entity_query, time.time()-start_t)
    return True
