"""Lucas grounding router public API.

Deterministic screen-coordinate resolution for mouse control:
AT-SPI a11y tree -> OCR -> template match -> targeted vision crop.
"""

from __future__ import annotations

from .confirms import clear_pending_confirmations, is_destructive
from .models import (
    SOURCES,
    SOURCE_A11Y,
    SOURCE_NONE,
    SOURCE_OCR,
    SOURCE_TEMPLATE,
    SOURCE_VISION,
    GroundingResult,
    WordBox,
)
from .resolver import resolve_intent, router_click
from .verify import clamp, verify_after_click

__all__ = [
    "GroundingResult",
    "WordBox",
    "SOURCES",
    "SOURCE_A11Y",
    "SOURCE_NONE",
    "SOURCE_OCR",
    "SOURCE_TEMPLATE",
    "SOURCE_VISION",
    "resolve_intent",
    "router_click",
    "is_destructive",
    "clear_pending_confirmations",
    "verify_after_click",
    "clamp",
]
