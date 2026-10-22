"""Search LUCAS's long-term semantic memory by meaning."""

from __future__ import annotations

from core.logger import get_logger
from memory import semantic_memory

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "memory_recall",
    "description": (
        "Search LUCAS's long-term semantic memory by meaning. Use when the user "
        "asks what they told you before, wants to recall something from past "
        "conversations, or says 'remember when' / 'do you remember'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": 'Set to "browse" to open the Memories window in the web UI',
            },
            "query": {
                "type": "STRING",
                "description": "What to search memories for",
            },
            "k": {
                "type": "NUMBER",
                "description": "Max results to return (1-10, default 3)",
            },
        },
        "required": ["query"],
    },
}


def memory_recall(*, parameters: dict, player=None, speak=None) -> str:
    """Execute the memory_recall tool and return a human-readable result."""
    action = (parameters.get("action") or "").lower().strip()
    if action == "browse":
        opener = getattr(player, "open_memories", None)
        if not callable(opener):
            return "The memories browser is only available in the web UI."
        opener({})
        return "Opening your memories."

    query = (parameters.get("query") or "").strip()
    if not query:
        return "What should I search my memories for?"

    try:
        k = max(1, min(10, int(parameters.get("k", 3))))
    except (TypeError, ValueError):
        k = 3

    try:
        results = semantic_memory.recall(query, k=k)
    except Exception as e:
        logger.warning("memory_recall failed: %s", e)
        return "Something went wrong while searching my memories."

    if not results:
        return "I don't have any memories matching that yet."
    joined = "\n".join(f"- {item}" for item in results)
    return f"Here is what I remember:\n{joined}"
