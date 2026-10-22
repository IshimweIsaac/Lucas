# web_search.py
from __future__ import annotations

import re
import json
import datetime
import urllib.request
import urllib.error

from memory.config_manager import get_tavily_keys

from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Searches the web for any information.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query":  {"type": "STRING", "description": "Search query"},
            "mode":   {"type": "STRING", "description": "search (default) or compare"},
            "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
            "aspect": {"type": "STRING", "description": "price | specs | reviews"},
            "topic":  {"type": "STRING", "description": "general or news"},
        },
        "required": ["query"],
    },
}

# ---------------------------------------------------------------------------
# Tavily key rotation — round-robin index persists across calls in one session
# ---------------------------------------------------------------------------
_tavily_key_index = 0


def _tavily_search_single(query: str, api_key: str, topic: str = "general") -> str:
    """Hit Tavily with one key. Raises on failure."""
    url = "https://api.tavily.com/search"

    # Inject current time context to help with "today", "last night" queries
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contextualized_query = f"{query} (Current date and time: {current_time})"

    payload = {
        "api_key": api_key,
        "query": contextualized_query,
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": 5
    }
    if topic == "news":
        payload["topic"] = "news"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        resp_data = json.loads(response.read().decode("utf-8"))
        answer = resp_data.get("answer")
        if answer:
            return answer

        # Fallback if no synthesized answer
        results = resp_data.get("results", [])
        if not results:
            return "Tavily returned no results."

        lines = [f"Tavily Search Results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', '')}")
            lines.append(f"   {r.get('content', '')[:300]}...")
            lines.append(f"   URL: {r.get('url', '')}\n")
        return "\n".join(lines).strip()


def _is_key_exhausted(error: Exception) -> bool:
    """Check if the error indicates a quota/rate-limit problem."""
    low = str(error).lower()
    return any(tok in low for tok in ("429", "quota", "rate", "limit", "exceeded", "403"))


def _tavily_search(query: str, topic: str = "general") -> str:
    """Try all Tavily keys with rotation. Raises if ALL keys fail."""
    global _tavily_key_index
    keys = get_tavily_keys()
    if not keys:
        raise RuntimeError("No Tavily API keys configured.")

    start = _tavily_key_index % len(keys)
    last_err: Exception | None = None

    for i in range(len(keys)):
        idx = (start + i) % len(keys)
        key = keys[idx]
        masked = f"{key[:12]}...{key[-4:]}"
        try:
            result = _tavily_search_single(query, key, topic=topic)
            # Success — next call starts with the NEXT key to spread usage
            _tavily_key_index = (idx + 1) % len(keys)
            logger.info("🔑 Used key %d/%d (%s)", idx + 1, len(keys), masked)
            return result
        except Exception as e:
            last_err = e
            if _is_key_exhausted(e):
                logger.warning("Key %d/%d exhausted (%s) — rotating...", idx + 1, len(keys), masked)
                continue
            else:
                # Non-quota error (network, bad request, etc.) — don't rotate
                raise

    # All keys exhausted
    raise RuntimeError(
        f"All {len(keys)} Tavily API keys exhausted. Last error: {last_err}"
    )


# ---------------------------------------------------------------------------
# DuckDuckGo fallback
# ---------------------------------------------------------------------------

def _ddg_client():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        from duckduckgo_search import DDGS
        return DDGS


def _collect_ddg(iterator, max_results: int) -> list[dict]:
    results: list[dict] = []
    for r in iterator:
        results.append(
            {
                "title": r.get("title", ""),
                "snippet": r.get("body", r.get("snippet", "")),
                "url": r.get("href", r.get("url", "")),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _looks_like_news(query: str) -> bool:
    return bool(re.search(r"\bnews\b", query, re.IGNORECASE))


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    DDGS = _ddg_client()
    results: list[dict] = []

    with DDGS() as ddgs:
        try:
            results = _collect_ddg(
                ddgs.text(query, max_results=max_results, region="wt-wt"),
                max_results,
            )
        except Exception as e:
            logger.warning("DDG text error: %s", e)

        if not results and _looks_like_news(query):
            try:
                results = _collect_ddg(
                    ddgs.news(query, max_results=max_results),
                    max_results,
                )
            except Exception as e:
                logger.warning("DDG news error: %s", e)

        if not results:
            try:
                results = _collect_ddg(ddgs.text(query, max_results=max_results), max_results)
            except Exception as e:
                logger.warning("DDG text (no region) error: %s", e)

    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Compare mode
# ---------------------------------------------------------------------------

def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compare {', '.join(items)} in terms of {aspect}. "
        "Give specific facts and data."
    )
    try:
        return _tavily_search(query)
    except Exception as e:
        logger.warning("Tavily compare failed: %s — falling back to DDG", e)

    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparison — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def web_search(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query = params.get("query", "").strip()
    mode = params.get("mode", "search").lower().strip()
    items = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"
    topic = (params.get("topic") or "general").strip().lower()
    if topic not in ("general", "news"):
        topic = "general"

    if not query and not items:
        return "Please provide a search query, sir."

    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")

    logger.info("🔍 Query: %r  Mode: %s", query, mode)

    try:
        if mode == "compare" and items:
            logger.info("📊 Comparing: %s", items)
            result = _compare(items, aspect)
            logger.info("✅ Compare done.")
            return result

        logger.info("🌐 Trying Tavily (with key rotation)...")
        try:
            result = _tavily_search(query, topic=topic)
            logger.info("✅ Tavily OK.")
            return result
        except Exception as e:
            logger.warning("⚠️ Tavily failed: %s — falling back to DDG...", e)

        logger.info("🌐 Trying DDG...")
        results = _ddg_search(query)
        result = _format_ddg(query, results)
        logger.info("✅ DDG: %d result(s).", len(results))
        return result

    except Exception as e:
        logger.error("❌ All backends failed: %s", e)
        return f"Search failed, sir: {e}"
