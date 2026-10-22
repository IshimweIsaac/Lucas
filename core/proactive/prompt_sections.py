"""Proactive prompt section for the Live system instruction.

Always appends the persona guardrail block; adds a bounded "current thoughts"
card when a pending engagement exists so the model has context to follow up
naturally (rather than repeating).
"""

from __future__ import annotations

from core.logger import get_logger
from core.proactive import engagement_store
from core.proactive import persona

logger = get_logger(__name__)

_MAX_THOUGHTS_CHARS = 600


def current_card() -> dict | None:
    """Most recent pending engagement (queued/spoken), if any."""
    entry = engagement_store.last_engagement()
    if entry and entry.get("status") in {"queued", "spoken"}:
        return entry
    return None


def format_proactive_section() -> str:
    """Persona block plus an optional current-thoughts card."""
    section = persona.persona_block()
    card = current_card()
    if card:
        body = (card.get("body") or card.get("title") or "").strip()
        if body:
            section += (
                "\n\n[LUCAS PROACTIVE - CURRENT THOUGHTS]\n"
                + body[:_MAX_THOUGHTS_CHARS]
            )
    return section