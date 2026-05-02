import re
from typing import Optional, Dict, Any
import os

# optional deps
try:
	from duckduckgo_search import DDGS
except Exception:
	DDGS = None

try:
	import requests
except Exception:
	requests = None


def ddg_search(query: str, logger, max_results: int = 10):
	"""DuckDuckGo search using duckduckgo_search package."""
	if DDGS is None:
		logger.debug("ddg_search: duckduckgo_search not available")
		return []

	try:
		logger.debug("ddg_search: querying DDG for %r", query)
		results = []
		with DDGS() as ddgs:
			for r in ddgs.text(query, max_results=max_results):
				results.append({
					"title": r.get("title") or query,
					"snippet": r.get("body") or "",
					"url": r.get("href") or ""
				})
		logger.debug("ddg_search: got %d results", len(results))
		return results
	except Exception as exc:
		logger.exception("ddg_search: failed: %s", exc)
		return []


def handle_search_branch(question: str, q_lower: str, response: Dict[str, Any], logger, apps: Optional[list]=None, geo: Optional[dict]=None) -> bool:
	"""
	Handle the 'search'/'find' assistant branch.
	Mutates 'response' in-place and returns True when handled.
	"""
	logger.debug("handle_search_branch: entry question=%r q_lower=%r", question, q_lower)

	m = re.search(r"(search for|find|look up|look for)\s+(.+)", q_lower)
	if m:
		question = m.group(2).strip().strip(" ?.")
		logger.debug("handle_search_branch: refined question=%r", question)

	# --- 1. Try SearX (if explicitly enabled) ---
	use_searx = os.getenv("USE_SEARX") == "1"
	if use_searx and requests is not None:
		import urllib.parse
		searx_base = os.getenv("SEARX_URL", "http://localhost:8080/")
		search_path = urllib.parse.urljoin(searx_base, "search")
		params = {"q": question, "format": "json", "pageno": 1}

		try:
			logger.debug("handle_search_branch: querying searx at %s", search_path)
			resp = requests.get(search_path, params=params, timeout=6)
			resp.raise_for_status()
			data = resp.json()

			results = []
			for r in data.get("results", [])[:10]:
				results.append({
					"title": r.get("title") or question,
					"snippet": r.get("content") or r.get("snippet") or "",
					"url": r.get("url") or r.get("link") or ""
				})

			if results:
				logger.debug("handle_search_branch: using searx results")
				_attach_results(response, question, results)
				return True

		except Exception as exc:
			logger.exception("handle_search_branch: searx failed: %s", exc)

	# --- 2. Try DuckDuckGo ---
	results = ddg_search(question, logger)
	if results:
		logger.debug("handle_search_branch: using DDG results")
		_attach_results(response, question, results)
		return True

	# --- 3. Final fallback ---
	logger.debug("handle_search_branch: using fallback results")
	_attach_results(response, question, [
		{"title": "Result 1", "snippet": "A brief summary...", "url": "https://example.com/r1"},
		{"title": "Result 2", "snippet": "Another summary...", "url": "https://example.com/r2"}
	])
	return True


def _attach_results(response: Dict[str, Any], question: str, results: list):
	"""Helper to keep response formatting consistent."""
	response["speech"] = f"Here’s what I found for {question}."
	response["display_markdown"] = f"Here’s what I found for **{question}**."
	response["cards"].append({
		"type": "search",
		"results": results
	})