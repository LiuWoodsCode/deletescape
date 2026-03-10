import re
from typing import Optional, Dict, Any
import os
import urllib.parse

# add requests import in a safe way so missing dependency is handled
try:
	import requests
except Exception:
	requests = None

def handle_search_branch(question: str, q_lower: str, response: Dict[str, Any], logger, apps: Optional[list]=None, geo: Optional[dict]=None) -> bool:
	"""
	Handle the 'search'/'find' assistant branch.
	Mutates 'response' in-place and returns True when the branch was handled.
	"""
	logger.debug("handle_search_branch: entry question=%r q_lower=%r", question, q_lower)
	m = re.search(r"(search for|find|look up|look for)\s+(.+)", q_lower)
	if m:
		question = m.group(2).strip().strip(" ?.")
		logger.debug("handle_search_branch: refined question=%r", question)

	# If env requests searx usage, try to query searxng instance
	use_searx = os.getenv("USE_SEARX") == "1"
	if use_searx and requests is not None:
		# My SearXNG instance hasn't been running for some time
		# This should probably be either Google CSE or DuckDuckGo
		searx_base = os.getenv("SEARX_URL", "http://pixelwiki.tail38c28.ts.net/searxng/")
		search_path = urllib.parse.urljoin(searx_base, "search")
		params = {"q": question, "format": "json", "pageno": 1}
		try:
			logger.debug("handle_search_branch: querying searx at %s params=%s", search_path, params)
			resp = requests.get(search_path, params=params, timeout=6)
			resp.raise_for_status()
			data = resp.json()
			# searxng returns a 'results' list; each item often has 'title', 'content' or 'snippet', and 'url'
			results = []
			for r in data.get("results", [])[:10]:
				title = r.get("title") or r.get("id") or question
				snippet = r.get("content") or r.get("snippet") or ""
				url = r.get("url") or r.get("link") or ""
				results.append({"title": title, "snippet": snippet, "url": url})
			if results:
				response["speech"] = f"Here’s what I found for {question}."
				response["display_markdown"] = f"Here’s what I found for **{question}**."
				response["cards"].append({
					"type": "search",
					"results": results
				})
				logger.debug("handle_search_branch: appended searx search card with %d results", len(results))
				return True
			else:
				logger.debug("handle_search_branch: searx returned no results, falling back")
		except Exception as exc:
			logger.exception("handle_search_branch: searx request failed: %s", exc)
			# fall through to fallback behavior

	# fallback / default behavior
	response["speech"] = f"Here’s what I found for {question}."
	response["display_markdown"] = f"Here’s what I found for **{question}**."
	response["cards"].append({
		"type": "search",
		"results": [
			{"title": "Result 1", "snippet": "A brief summary...", "url": "https://example.com/r1"},
			{"title": "Result 2", "snippet": "Another summary...", "url": "https://example.com/r2"}
		]
	})
	logger.debug("handle_search_branch: appended search card for question=%r", question)
	return True
