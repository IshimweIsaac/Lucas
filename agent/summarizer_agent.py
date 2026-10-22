"""Gemini summarizer agent — uses rotated keys from ``config/agent_keys.json``."""

from __future__ import annotations

from dataclasses import dataclass

from agent.key_manager import get_key_manager
from core.logger import get_logger
from memory.coding_model import get_search_model
from memory.gemini_text import generate_text_with_agent_key

logger = get_logger(__name__)

_SUMMARY_SYSTEM = """\
You are a concise summarizer for the Lucas coding assistant.
Return a clear summary within the requested character limit. No preamble.
"""


@dataclass
class SummaryResult:
    text: str
    summary: str
    model: str
    max_chars: int

    @property
    def ok(self) -> bool:
        return bool(self.summary.strip())


class SummarizerAgent:
    """Gemini-backed summarizer using round-robin agent keys."""

    def __init__(self, *, model: str | None = None, provider: str = "gemini"):
        self.model = (model or get_search_model()).strip()
        self.provider = provider
        self._keys = get_key_manager()

    def summarize(self, text: str, *, max_chars: int = 500) -> SummaryResult:
        text = (text or "").strip()
        if not text:
            return SummaryResult(text="", summary="", model=self.model, max_chars=max_chars)

        if not self._keys.has_keys(self.provider):
            raise RuntimeError(
                f"No {self.provider} keys in config/agent_keys.json. "
                "Add keys there for swarm agents (not api_keys.json)."
            )

        prompt = (
            f"Summarize in at most {max_chars} characters:\n\n{text[:12000]}"
        )
        logger.info("[SummarizerAgent] model=%s max_chars=%s", self.model, max_chars)
        summary = generate_text_with_agent_key(
            self.model,
            prompt,
            provider=self.provider,
            system_instruction=_SUMMARY_SYSTEM,
        )
        return SummaryResult(
            text=text,
            summary=summary.strip()[:max_chars],
            model=self.model,
            max_chars=max_chars,
        )


def run_summarize(text: str, max_chars: int = 500) -> str:
    """Convenience wrapper returning summary text or an error message."""
    try:
        return SummarizerAgent().summarize(text, max_chars=max_chars).summary
    except Exception as exc:
        logger.warning("[SummarizerAgent] failed: %s", exc)
        return f"Summarizer error: {exc}"
