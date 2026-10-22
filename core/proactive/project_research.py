"""Interest-driven research — bounded web research via actions.web_search.

The automated path (`maybe_research`) is budget-limited by the governor's web
counter; the manual path (`research_topic`) used by the `proactive` tool is
never throttled. Results are trimmed and scrubbed so secrets never leak.
"""

from __future__ import annotations

import re

from core.logger import get_logger
from core.proactive import governor
from core.proactive import research_ideas_store

logger = get_logger(__name__)

DEFAULT_MAX_CHARS = 2000

_KEY_PATTERN = re.compile(
    r"(?:(?:sk-|tvly-|ghp_|gho_|AIza|AKIA|xox[baprs]-)[A-Za-z0-9_\-]{8,}"
    r"|[A-Za-z0-9_\-]{32,})"
)


def _trim_result(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Trim to *max_chars* and scrub anything that looks like a secret token."""
    cleaned = _KEY_PATTERN.sub("[redacted]", text or "")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _search_topic(topic: str) -> str:
    """Run a web search for *topic* (Tavily news preferred, DDG fallback)."""
    try:
        from actions.web_search import web_search

        result = web_search(parameters={"query": topic, "topic": "news"})
    except TypeError:
        # Defensive: web_search without the topic param (older variant).
        try:
            from actions.web_search import web_search

            result = web_search(parameters={"query": topic})
        except Exception as exc:
            logger.warning("proactive: research fallback search failed (%s)", exc)
            return f"Research failed for topic: {topic}"
    except Exception as exc:
        logger.warning("proactive: research search failed (%s)", exc)
        return f"Research failed for topic: {topic}"
    return _trim_result(result, DEFAULT_MAX_CHARS)


def maybe_research(
    cfg: dict | None = None,
    counters: dict | None = None,
) -> dict | None:
    """Automated research pass — consumes one web-search budget unit."""
    if governor.budget_left(cfg, counters, "web") <= 0:
        return None
    topic = research_ideas_store.pick_next_topic()
    if not topic:
        return None
    result = _search_topic(topic["topic"])
    research_ideas_store.mark_done(topic["id"], result=result)
    logger.info("proactive: researched topic %s (%s)", topic["id"], topic["topic"])
    return {"id": topic["id"], "topic": topic["topic"], "result": result}


def research_topic(topic: str, *, manual: bool = True) -> str:
    """Manual research — user-requested, never throttled by budget."""
    topic = (topic or "").strip()
    if not topic:
        return "Please provide a topic, sir."
    result = _search_topic(topic)
    # Persist as a breadcrumb in the engagement store so it is remembered.
    try:
        from core.proactive import engagement_store

        engagement_store.append_entry(
            {
                "kind": "research",
                "title": topic[:160],
                "body": result[:600],
                "score": 0.0,
                "source": "manual:research_topic",
                "status": "acknowledged",
            }
        )
    except Exception as exc:
        logger.warning("proactive: breadcrumb persist failed (%s)", exc)
    return result