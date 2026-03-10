from flask import Flask, request, jsonify
from datetime import datetime
import logging
import os
import time
from typing import Dict
import ssl
import re
import random
from branches.general import handle_general_branches
from branches.open import handle_open_branch
from branches.search import handle_search_branch
from branches.news import handle_news_branch
from branches.weather import handle_weather_branch
from branches.wikidata import handle_wikidata_branch
from branches.selfhelp import handle_selfhelp_branch
from branches.medical import handle_medical_branch
# New: call central auth server for token validation
import requests

app = Flask(__name__)

MIN_CLIENT_VERSION = "1.0.0"

# Auth config (use existing OAuth server; do not implement OAuth here)
AUTH_SERVER = os.getenv("AUTH_SERVER_URL", "http://100.124.161.53:5000")
REQUIRE_AUTH = os.getenv("CORTANA_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")

def validate_bearer_token(token: str):
    """Validate Bearer token via the central auth server's /userinfo endpoint."""
    if not token:
        return None
    try:
        ui = requests.get(f"{AUTH_SERVER}/userinfo", headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if ui.status_code == 200:
            return ui.json()
        logger.warning("Auth userinfo failed: %s %s", ui.status_code, ui.text[:200])
    except Exception as ex:
        logger.exception("Auth userinfo exception: %s", ex)
    return None

# --- super-duper verbose logging setup ---
LOG_LEVEL = os.getenv("CORTANA_LOG_LEVEL", "DEBUG").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(module)s:%(lineno)d %(message)s"
)
logger = logging.getLogger("cortana2")
logger.setLevel(LOG_LEVEL)
# Attach same handlers to Flask app.logger so Flask logs also use this format
for h in logging.getLogger().handlers:
    app.logger.addHandler(h)

@app.route("/sysreq", methods=["GET"])
def get_sysreq():
    """Return minimum supported client version."""
    return jsonify({
        "minimum_client_version": MIN_CLIENT_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

# New: simple whoami helper to test tokens
@app.route("/whoami", methods=["GET"])
def whoami():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(None, 1)[1].strip() if auth_header.lower().startswith("bearer ") else None
    userinfo = validate_bearer_token(token) if token else None
    if not userinfo:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": userinfo})

@app.route("/ask", methods=["POST"])
def ask_assistant():
    """
    POST /ask
    JSON Body Example:
    {
        "question": "What's the weather?",
        "geolocation": {"lat": 38.8, "lon": -77.3},
        "applications": ["Edge", "Spotify", "Calendar"]
    }
    """
    start_t = time.time()
    logger.debug("ask_assistant: incoming request from %s path=%s", request.remote_addr, request.path)

    # New: optional auth handling (use existing OAuth server)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split(None, 1)[1].strip() if auth_header.lower().startswith("bearer ") else None
    userinfo = validate_bearer_token(token) if token else None
    if REQUIRE_AUTH and not userinfo:
        logger.debug("ask_assistant: unauthorized (REQUIRE_AUTH enabled)")
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json(force=True)
        logger.debug("ask_assistant: payload=%s", data)
    except Exception:
        logger.exception("ask_assistant: failed to parse JSON")
        return jsonify({"error": "Invalid JSON"}), 400

    question = data.get("question", "").strip()
    geo = data.get("geolocation", {})
    apps = data.get("applications", [])

    logger.debug("ask_assistant: question=%r geolocation=%r applications=%r", question, geo, apps)
    if not question:
        logger.debug("ask_assistant: missing question in payload")
        return jsonify({"error": "Missing 'question'"}), 400

    # --- Base response ---
    response = {
        "question": question,
        "speech": None,
        "display_markdown": None,
        "url": None,
        "launch_app": None,
        "cards": [],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    # New: include auth context (if any)
    if userinfo:
        # Attach a sanitized subset of the auth server's userinfo to the response
        # sanitize values: return None for missing/empty consented fields
        def _clean(v):
            if v is None:
                return None
            if isinstance(v, str):
                v = v.strip()
                return v if v else None
            return v

        safe_user = {
            "name": _clean(userinfo.get("name")),
            "display_name": _clean(userinfo.get("display_name")),
            "picture": _clean(userinfo.get("picture")),
            "email": _clean(userinfo.get("email")),
            "last_login": _clean(userinfo.get("last_login")),
            "sub": _clean(userinfo.get("sub")),
            # normalize pronouns into a single object (if present)
            "pronouns": {
            "subject": _clean(userinfo.get("subject_pronouns") or (userinfo.get("pronouns") or {}).get("subject")),
            "object": _clean(userinfo.get("object_pronouns") or (userinfo.get("pronouns") or {}).get("object")),
            "possessive": _clean(userinfo.get("possessive_pronouns") or (userinfo.get("pronouns") or {}).get("possessive")),
            }
        }

        # If user declined pronouns (all None), remove the pronouns key
        if not any(safe_user["pronouns"].values()):
            safe_user.pop("pronouns")

        # Add a small manifest of which fields were actually provided (helps caller know consent)
        safe_user["provided_fields"] = [k for k, v in safe_user.items() if v is not None and k != "provided_fields"]

        response["user"] = safe_user

    q_lower = question.lower()
    logger.debug("ask_assistant: q_lower=%r", q_lower)

    # 1️⃣ Weather card
    if "weather" in q_lower:
        logger.debug("ask_assistant: matched branch=weather (delegating to weather branch)")
        handled = handle_weather_branch(question, q_lower, response, logger, apps=apps, geo=geo)
        if handled:
            return jsonify(response)

    # 2️⃣ News card
    elif "news" in q_lower:
        logger.debug("ask_assistant: matched branch=news (delegating to news branch)")
        handled = handle_news_branch(question, q_lower, response, logger, apps=apps, geo=geo)
        if handled:
            return jsonify(response)
    
    # 3️⃣ Search result card
    elif "search" in q_lower or "find" in q_lower:
        logger.debug("ask_assistant: matched branch=search/find")
        handled = handle_search_branch(question, q_lower, response, logger, apps=apps, geo=geo)
        if handled:
            return jsonify(response)
    
    # 4️⃣ App or URL open
    elif "open" in q_lower:
        logger.debug("ask_assistant: matched branch=open")
        handled = handle_open_branch(question, q_lower, response, logger, apps=apps, geo=geo)
        if handled:
            return jsonify(response)
    # 2.25️⃣ Medical emergencies handling (high priority)
    logger.debug("ask_assistant: delegating to medical branch")
    handled = handle_medical_branch(question, q_lower, response, logger, apps=apps, geo=geo)
    if handled:
        return jsonify(response)
    # 2.5️⃣ Wikidata entity card
    # --- New: Wikidata / entity lookup handling ---
    logger.debug("ask_assistant: delegating to wikidata branch")
    handled = handle_wikidata_branch(question, q_lower, response, logger, apps=apps, geo=geo, start_t=start_t)
    if handled:
        return jsonify(response)

    # Self-harm / crisis handling
    logger.debug("ask_assistant: delegating to selfhelp branch")
    handled = handle_selfhelp_branch(question, q_lower, response, logger, apps=apps, geo=geo)
    if handled:
        return jsonify(response)

    # Fun ones
    handled = handle_general_branches(question, q_lower, response, logger, apps=apps, geo=geo)
    if handled:
        return jsonify(response)
    
    else:
        logger.debug("ask_assistant: matched branch=fallback")

        fallback_speech = [
            "Hmm… I'm not sure about that yet.",
            "I'm still learning, and that one's new to me.",
            "I don't think I know the answer to that just yet.",
            "That's a tricky one. I'm still figuring it out.",
            "I might need a little more training before I can answer that."
        ]

        fallback_display = [
            f"**I'm not sure what you mean by \"{question}\".**\n\nI'm still learning, but I'll get smarter over time!",
            f"**That one stumped me:** \"{question}\"\n\nGive me a bit more training and I'll try again later.",
            f"**I couldn't quite figure out \"{question}\".**\n\nI'm still learning new things every day.",
            f"**Hmm… \"{question}\" doesn't ring a bell yet.**\n\nBut I'm getting better all the time!",
            f"**I don't know that one yet:** \"{question}\".\n\nAsk me something else while I keep learning!"
        ]

        response["speech"] = random.choice(fallback_speech)
        response["display_markdown"] = random.choice(fallback_display)

    logger.debug(
        "ask_assistant: final response cards=%d elapsed=%.3fs",
        len(response["cards"]),
        time.time() - start_t
    )

    return jsonify(response)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Cortana 2.0 Backend Prototype",
        "version": "0.4",
        "description": "Voice assistant backend with separate speech and markdown, and card support.",
        "endpoints": ["/sysreq", "/ask", "/whoami"],
        "auth": {
            "auth_server": AUTH_SERVER,
            "require_auth": REQUIRE_AUTH
        }
    })


if __name__ == "__main__":
    # Move off 5000 to avoid colliding with the OAuth server
    port = int(os.getenv("CORTANA_PORT", "5500"))
    logger.info("Starting Cortana2 backend on 0.0.0.0:%d (debug mode), AUTH_SERVER=%s REQUIRE_AUTH=%s", port, AUTH_SERVER, REQUIRE_AUTH)
    app.run(host="0.0.0.0", port=port, debug=True)