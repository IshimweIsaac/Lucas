from __future__ import annotations

import json
import re
from typing import Any

from core.logger import get_logger
from memory.gemini_text import generate_text_with_agent_key

logger = get_logger(__name__)


class TaskClassifierAgent:
    """Classify a coding task goal into a structured description."""

    def __init__(self, model: str = "gemini-3.1-flash-lite"):
        self.model = model

    def classify(self, goal: str, job_type: Any = None) -> dict[str, Any]:
        """Return a JSON-compatible dict describing the task."""
        _ = job_type  # reserved for future prompt context
        prompt = (
            "Classify the following coding task goal.\n"
            "Return a JSON object with:\n"
            '- complexity: "low" | "medium" | "high"\n'
            '- type: "bugfix" | "feature" | "refactor" | "research"\n'
            "- needs_research: boolean\n"
            "- skip_plan: boolean\n"
            "- reasoning: string\n\n"
            f"Goal: {goal}"
        )
        raw = generate_text_with_agent_key(
            model=self.model,
            contents=prompt,
        )
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse classification JSON: {raw}")
            return {
                "complexity": "medium",
                "type": "feature",
                "needs_research": False,
                "skip_plan": False,
                "reasoning": "Parsing failed, defaulting.",
            }
