import requests
import re
import json
from urllib.parse import quote

SUGGEST_URL_FIREFOX = "https://suggestqueries.google.com/complete/search"
SUGGEST_URL_CHROME = "https://www.google.com/complete/search"
KG_URL = "https://trends.google.com/trends/api/autocomplete"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

def autocomplete(query, client="chrome", timeout=5, include_kg=False):
    """
    Fetch Google autocomplete suggestions for a query.
    
    Args:
        query: Search query string
        client: Client type - "chrome" or "firefox" (default: "chrome")
        timeout: Request timeout in seconds
        include_kg: Whether to include Knowledge Graph data (default: False)
    
    Returns:
        If include_kg is False: List of suggestion strings
        If include_kg is True: Dict with suggestions, kg_results, and full_data
    """
    suggest_url = SUGGEST_URL_CHROME if client == "chrome" else SUGGEST_URL_FIREFOX
    
    params = {
        "client": client,
        "q": query
    }

    headers = {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0)"
        }
    resp = requests.get(suggest_url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()

    data = resp.json()
    suggestions = data[1] if len(data) > 1 else []
    
    if not include_kg:
        return suggestions
    
    # Include Knowledge Graph data
    kg_results = _get_knowledge_graph_results(query, timeout)
    
    return {
        "suggestions": suggestions,
        "kg_results": kg_results,
        "raw_data": data
    }


def _get_knowledge_graph_results(query, timeout=5):
    """
    Fetch Google Knowledge Graph results for a query.
    
    Returns a list of entity dicts with details from Wikidata.
    """
    try:
        kg_to_query = KG_URL + "/" + quote(query)
        print(kg_to_query)
        headers = {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0)"
        }
        resp = requests.get(kg_to_query, timeout=timeout, headers=headers)
        resp.raise_for_status()
        
        # The response has a security prefix like ")]}'" followed by JSON
        # Find where the JSON actually starts (first { or [)
        text = resp.text
        json_start = text.find('{')
        if json_start > 0:
            text = text[json_start:]
        
        # Use raw_decode to parse only the first valid JSON object
        data = json.JSONDecoder().raw_decode(text)[0]
        
        # Extract topics from the response
        topics = data.get("default", {}).get("topics", [])
        
        # Enrich each topic with Wikidata information
        enriched_topics = []
        for topic in topics:
            mid = topic.get("mid")
            title = topic.get("title")
            type_str = topic.get("type")
            
            if mid:
                wikidata_info = _get_wikidata_info(mid, title, type_str, timeout)
                enriched_topics.append(wikidata_info)
        
        return enriched_topics
    
    except Exception as e:
        print(f"Error fetching Knowledge Graph results: {e}")
        return []


def _get_wikidata_info(google_mid, title, type_str, timeout=5):
    """
    Query Wikidata to get detailed information about an entity using its Google MID.
    
    Args:
        google_mid: Google Knowledge Graph entity ID (e.g., "/g/11pbtt3wfq")
        title: Entity title from Knowledge Graph
        type_str: Entity type from Knowledge Graph
        timeout: Request timeout in seconds
    
    Returns:
        Dict with entity information including image and description
    """
    try:
        # Query Wikidata using the Google MID (P2671 property)
        sparql_query = f"""
        SELECT ?item ?itemLabel ?image ?description WHERE {{
          ?item wdt:P2671 "{google_mid}" .
          OPTIONAL {{ ?item wikibase:commonsMedia ?image . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """
        
        headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": "StickerbombBot/1.0 (contact: high16hate@outlook.com)"
        }
        
        data = {
            "query": sparql_query
        }
        
        resp = requests.post(WIKIDATA_SPARQL_URL, data=data, headers=headers, timeout=timeout)
        resp.raise_for_status()
        
        result = resp.json()
        bindings = result.get("results", {}).get("bindings", [])
        
        if bindings:
            binding = bindings[0]
            item_uri = binding.get("item", {}).get("value", "")
            item_label = binding.get("itemLabel", {}).get("value", title)
            image = binding.get("image", {}).get("value", "")
            description = binding.get("description", {}).get("value", "")
            
            # If type is generic, use description; otherwise use type as description
            generic_types = {"Topic", "Author", "Person", "Thing"}
            if type_str in generic_types:
                final_description = description
            else:
                final_description = type_str
            
            wikidata_id = item_uri.replace("http://www.wikidata.org/entity/", "") if item_uri else ""
            
            return {
                "title": item_label,
                "google_mid": google_mid,
                "wikidata_id": wikidata_id,
                "description": final_description,
                "image": image,
                "type": type_str
            }
    
    except Exception as e:
        print(f"Error querying Wikidata for {google_mid}: {e}")
    
    # Fallback if Wikidata query fails
    return {
        "title": title,
        "google_mid": google_mid,
        "wikidata_id": "",
        "description": type_str if type_str not in {"Topic", "Author", "Person", "Thing"} else "",
        "image": "",
        "type": type_str
    }


if __name__ == "__main__":
    # Demo: Basic autocomplete
    print("=== Basic Autocomplete ===")
    for s in autocomplete("hello"):
        print("-", s)
    
    # Demo: Autocomplete with Knowledge Graph
    print("\n=== Autocomplete with Knowledge Graph ===")
    result = autocomplete("maia arson", include_kg=True)
    print(json.dumps(result, indent=2))
