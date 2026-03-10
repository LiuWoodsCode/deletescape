from flask import Flask, request, jsonify, abort
import os
from kb import LocalWikidata  # your LocalWikidata class file
from flask import send_from_directory
import requests

app = Flask(__name__)
kb = LocalWikidata()

@app.route("/w/api.php")
def wikidata_api():
    """Imitate Wikidata API endpoints (wbsearchentities, wbgetentities)."""
    action = request.args.get("action")
    fmt = request.args.get("format", "json")

    # --- wbsearchentities ---
    if action == "wbsearchentities":
        query = request.args.get("search")
        lang = request.args.get("language", "en")
        limit = int(request.args.get("limit", 10))
        if not query:
            abort(400, "Missing ?search parameter")
        results = kb.wbsearchentities(query, language=lang, limit=limit)
        return jsonify(results)

    # --- wbgetentities ---
    elif action == "wbgetentities":

        ids = request.args.get("ids")
        if not ids:
            abort(400, "Missing ?ids parameter")
        # Forward all query parameters to Wikidata with UA header
        wikidata_url = "https://www.wikidata.org/w/api.php"
        params = dict(request.args)
        headers = {
            "User-Agent": "LocalWikidataCompatServer/1.0 (contact@example.com)",
            # Ask for identity to avoid upstream gzip and simplify proxying
            "Accept-Encoding": "identity",
        }
        resp = requests.get(wikidata_url, params=params, headers=headers, timeout=10)
        # requests has already decompressed resp.content if it was encoded.
        # Remove encoding-related and hop-by-hop headers so clients don't try to decode again.
        filtered_headers = []
        for k, v in resp.headers.items():
            kl = k.lower()
            if kl in ("content-encoding", "content-length", "transfer-encoding", "connection"):
                continue
            filtered_headers.append((k, v))
        return (resp.content, resp.status_code, filtered_headers)

    else:
        abort(400, f"Unsupported action {action}")

@app.route("/wiki/Special:EntityData/<entity_id>.json")
def wikidata_entity_json(entity_id):
    """Return a single entity as Wikidata does."""
    ent = kb.entities.get(entity_id)
    if not ent:
        abort(404, f"No such entity {entity_id}")
    return jsonify({"entities": {entity_id: ent}})

MEDIA_DIR = "./static/photos"

@app.route("/wiki/Special:FilePath/<path:filename>")
def serve_media(filename):
    """Serve local image files for P18 (commonsMedia) claims."""
    path = os.path.join(MEDIA_DIR, filename)
    if not os.path.exists(path):
        abort(404, f"File not found: {filename}")
    return send_from_directory(MEDIA_DIR, filename)

@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": str(err)}), 400


@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": str(err)}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3192))
    print(f"Local Wikidata server running at http://localhost:{port}/w/api.php")
    app.run(host="0.0.0.0", port=port, debug=True)
