"""Data models for the Lucas grounding router.

A grounding result describes where a UI element was located on screen and
which strategy found it (a11y tree, OCR, template match, vision crop).
"""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_NONE = "none"
SOURCE_A11Y = "a11y"
SOURCE_OCR = "ocr"
SOURCE_TEMPLATE = "template"
SOURCE_VISION = "vision"

SOURCES = (SOURCE_A11Y, SOURCE_OCR, SOURCE_TEMPLATE, SOURCE_VISION, SOURCE_NONE)


@dataclass
class WordBox:
    """A word detected by OCR with its bounding box in image pixels."""

    text: str
    x: int  # left
    y: int  # top
    w: int
    h: int
    conf: float = 0.0

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass
class GroundingResult:
    """Outcome of resolving a UI element description to screen coordinates."""

    found: bool
    source: str = SOURCE_NONE
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    label: str = ""
    note: str = ""
