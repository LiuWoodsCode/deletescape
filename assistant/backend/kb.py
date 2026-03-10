import json
import os
import requests
from typing import Dict, Any, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROPS_DIR = os.path.join(DATA_DIR, "prop")  # per-property files live here

HEADERS = {
    "User-Agent": (
        "Cortana2-LocalWikidata/1.0 "
        "(https://github.com/PixelProwler/Cortana2; contact: pixelprowlertest@outlook.com)"
    )
}


class LocalWikidata:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.properties: Dict[str, Dict[str, Any]] = {}
        self.load_all()

    # --- Initialization ------------------------------------------------------

    def load_all(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(PROPS_DIR, exist_ok=True)

        # Load cached properties from data/prop/*.json
        self.properties.clear()
        for file in os.listdir(PROPS_DIR):
            if file.endswith(".json"):
                try:
                    with open(os.path.join(PROPS_DIR, file), "r", encoding="utf-8") as f:
                        prop = json.load(f)
                        if isinstance(prop, dict) and "id" in prop:
                            self.properties[prop["id"]] = prop
                except Exception as e:
                    print(f"[WARN] Failed to load property {file}: {e}")

        # Load entities
        for file in os.listdir(self.data_dir):
            if file.startswith("Q") and file.endswith(".json"):
                with open(os.path.join(self.data_dir, file), "r", encoding="utf-8") as f:
                    entity = json.load(f)
                    self.entities[entity["id"]] = entity

    def save_properties(self):
        # Save each property as its own file in data/prop/{pid}.json
        os.makedirs(PROPS_DIR, exist_ok=True)
        for pid, prop in self.properties.items():
            try:
                with open(os.path.join(PROPS_DIR, f"{pid}.json"), "w", encoding="utf-8") as f:
                    json.dump(prop, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[WARN] Failed to save property {pid}: {e}")

    # --- Property Handling ---------------------------------------------------

    def fetch_property(self, pid: str) -> Optional[Dict[str, Any]]:
        """Download a property definition from Wikidata."""
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{pid}.json"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                print(f"[WARN] Property {pid} not found (HTTP {r.status_code})")
                return None
            data = r.json()
            ent = data["entities"][pid]
            if ent.get("type") != "property":
                return None
            prop = {
                "id": pid,
                "label": ent["labels"].get("en", {}).get("value", ""),
                "description": ent["descriptions"].get("en", {}).get("value", ""),
                "datatype": ent.get("datatype", "")
            }
            self.properties[pid] = prop
            self.save_properties()
            print(f"[+] Downloaded {pid}: {prop['label']}")
            return prop
        except Exception as e:
            print(f"[ERROR] Could not fetch {pid}: {e}")
            return None

    def get_property_label(self, pid: str) -> str:
        """Get a property label, fetching it if missing."""
        if pid not in self.properties:
            self.fetch_property(pid)
        return self.properties.get(pid, {}).get("label", pid)

    # --- Core Wikidata-like API ---------------------------------------------

    def wbsearchentities(self, search: str, language: str = "en", limit: int = 10):
        results = []
        search_lower = search.lower()
        for entity in self.entities.values():
            label = entity.get("labels", {}).get(language, {}).get("value", "")
            desc = entity.get("descriptions", {}).get(language, {}).get("value", "")
            aliases = [a["value"] for a in entity.get("aliases", {}).get(language, [])]

            if any(search_lower in s.lower() for s in [label, desc] + aliases):
                results.append({
                    "id": entity["id"],
                    "label": label,
                    "description": desc
                })
            if len(results) >= limit:
                break
        return {"search": results}

    def wbgetentities(self, ids: List[str], language: str = "en"):
        entities = {}
        for qid in ids:
            e = self.entities.get(qid)
            if e:
                entities[qid] = e
        return {"entities": entities}

    # --- Entity Management ---------------------------------------------------

    def add_entity(self, entity: Dict[str, Any]):
        eid = entity["id"]
        self.entities[eid] = entity
        with open(os.path.join(self.data_dir, f"{eid}.json"), "w", encoding="utf-8") as f:
            json.dump(entity, f, indent=2, ensure_ascii=False)

    # --- Human-Readable Summary ---------------------------------------------

    def summarize(self, qid: str, language: str = "en") -> str:
        e = self.entities.get(qid)
        if not e:
            return f"No entity found for {qid}"

        label = e.get("labels", {}).get(language, {}).get("value", qid)
        desc = e.get("descriptions", {}).get(language, {}).get("value", "")
        out = [f"**{label}** — {desc}"]

        for pid, stmts in e.get("claims", {}).items():
            # Ensure property is fetched if missing
            if pid not in self.properties:
                self.fetch_property(pid)
            prop_label = self.get_property_label(pid)
            for stmt in stmts:
                dv = stmt["mainsnak"]["datavalue"]["value"]
                if isinstance(dv, dict) and "id" in dv:
                    val = dv["id"]
                else:
                    val = dv
                out.append(f"- {prop_label}: {val}")

        return "\n".join(out)
