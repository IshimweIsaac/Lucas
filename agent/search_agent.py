"""
Gemini search agent — text research using rotated keys from ``config/agent_keys.json``.

Separate from voice Live API (``config/api_keys.json``). Swarm research and other
agents should use this instead of inventing answers when web search is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.key_manager import get_key_manager
from core.logger import get_logger
from memory.coding_model import get_search_model
from memory.gemini_text import generate_text_with_agent_key

logger = get_logger(__name__)

_SEARCH_SYSTEM = """\
You are a focused research agent for the Lucas coding assistant.

Given a user goal and optional context (codebase notes, web snippets), produce:
1. A short direct answer (2-4 sentences).
2. Bullet list of actionable steps or facts (3-6 bullets).
3. Risks or unknowns (if any).

Be precise. Do not invent file paths or APIs. If unsure, say what to verify.
"""


@dataclass
class SearchResult:
    query: str
    answer: str
    provider: str
    model: str
    key_slot: int

    @property
    def ok(self) -> bool:
        return bool(self.answer.strip())


class SearchAgent:
    """Gemini-backed research using round-robin agent keys."""

    def __init__(self, *, model: str | None = None, provider: str = "gemini"):
        self.model = (model or get_search_model()).strip()
        self.provider = provider
        self._keys = get_key_manager()

    def search(
        self,
        query: str,
        *,
        context: str = "",
        goal: str = "",
    ) -> SearchResult:
        """Run one Gemini research call with the next agent key."""
        query = (query or "").strip()
        if not query:
            return SearchResult(query="", answer="", provider=self.provider, model=self.model, key_slot=0)

        if not self._keys.has_keys(self.provider):
            raise RuntimeError(
                f"No {self.provider} keys in config/agent_keys.json. "
                "Add keys there for swarm/search agents (not api_keys.json)."
            )

        parts = [f"Query: {query}"]
        if goal.strip():
            parts.append(f"Goal: {goal.strip()}")
        if context.strip():
            parts.append(f"Context:\n{context.strip()[:8000]}")

        logger.info("[SearchAgent] model=%s provider=%s", self.model, self.provider)
        answer = generate_text_with_agent_key(
            self.model,
            "\n\n".join(parts),
            provider=self.provider,
            system_instruction=_SEARCH_SYSTEM,
        )
        return SearchResult(
            query=query,
            answer=answer,
            provider=self.provider,
            model=self.model,
            key_slot=self._keys.key_count(self.provider),
        )


def run_search(query: str, *, context: str = "", goal: str = "") -> str:
    """Convenience wrapper returning answer text or an error message."""
    try:
        return SearchAgent().search(query, context=context, goal=goal).answer
    except Exception as exc:
        logger.warning("[SearchAgent] failed: %s", exc)
        return f"Search agent error: {exc}"
