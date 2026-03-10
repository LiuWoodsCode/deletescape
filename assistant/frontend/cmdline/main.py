import os
import json
import urllib.request
import urllib.parse
import urllib.error

DEFAULT_TIMEOUT = 8.0


def get_default_base_url():
    return os.getenv("CORTANA_BACKEND", "http://127.0.0.1:5500")


def fetch_url(url, method="GET", data=None, headers=None, timeout=DEFAULT_TIMEOUT):
    headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return {"status": resp.getcode(), "body": json.loads(body)}
            except Exception:
                return {"status": resp.getcode(), "body": body}

    except urllib.error.HTTPError as he:
        try:
            return {"status": he.code, "error": he.read().decode()}
        except Exception:
            return {"status": he.code, "error": str(he)}

    except Exception as e:
        return {"status": None, "error": str(e)}


def backend_ask(question):
    base_url = get_default_base_url()
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "ask")

    payload = {
        "question": question,
        "geolocation": {"lat": 0.0, "lon": 0.0},
        "applications": ["Edge", "Spotify"],
    }

    data = json.dumps(payload).encode("utf-8")

    result = fetch_url(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    if result.get("status") and isinstance(result.get("body"), dict):
        return result["body"]

    return {"error": result.get("error") or result.get("body")}


def print_response(resp):
    if "error" in resp:
        print(f"\n[error] {resp['error']}\n")
        return
    
    if resp.get("display_markdown"):
        print("\n--- TTS output ---")
        print(resp["speech"])
        
    if resp.get("display_markdown"):
        print("\n--- Markdown output ---")
        print(resp["display_markdown"])

    if resp.get("url"):
        print("\nurl:", resp["url"])

    if resp.get("launch_app"):
        print("\nlaunch_app:", resp["launch_app"])

    cards = resp.get("cards") or []
    if cards:
        print("\n--- cards ---")
        for c in cards:
            label = c.get("label") or "no label found"
            type = c.get("type") or "no type found"
            print(f"label: {label}")
            print(f"type: {type}")
            print(f"data: {c}")

    raw = str(resp)
    print("\n--- Raw response ---")
    print(f"{raw}")

def main():
    print("LumonVoice (terminal)")
    print("type 'exit' to quit\n")

    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        resp = backend_ask(question)
        print_response(resp)
        print()


if __name__ == "__main__":
    main()