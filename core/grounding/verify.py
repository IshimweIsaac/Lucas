"""Coordinate clamping and post-click verification.

verify_after_click is ADVISORY only: it never fails the tool. It re-checks,
after a click, whether the target element is still present (which suggests the
click may not have taken effect) for a11y and OCR sources only.
"""

from __future__ import annotations

import time

from core.logger import get_logger

from .atspi_tree import a11y_available, find_node
from .capture import capture_region, screen_size
from .ocr_grounding import match_words, ocr_words

logger = get_logger(__name__)

_VERIFY_DELAY_S = 0.8
_VERIFY_REGION_W = 600
_VERIFY_REGION_H = 400


def clamp(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    """Clamp (x, y) into 0 <= x < w, 0 <= y < h."""
    max_x = max(w - 1, 0)
    max_y = max(h - 1, 0)
    return (min(max(x, 0), max_x), min(max(y, 0), max_y))


def _verify_a11y(result) -> str:
    if not a11y_available():
        return ""
    if not result.label:
        return ""
    if find_node(result.label) is not None:
        return f"element still present at ({result.x}, {result.y})"
    return ""


def _verify_ocr(result) -> str:
    if not result.label:
        return ""
    size = screen_size()
    if size is None:
        sw, sh = 1920, 1080
    else:
        sw, sh = size
    left = result.x - _VERIFY_REGION_W // 2
    top = result.y - _VERIFY_REGION_H // 2
    captured = capture_region((left, top, _VERIFY_REGION_W, _VERIFY_REGION_H))
    if captured is None:
        return ""
    img = captured[0]
    words = ocr_words(img)
    if match_words(words, result.label) is not None:
        return f"element still present at ({result.x}, {result.y})"
    return ""


def verify_after_click(result, delay_s: float = _VERIFY_DELAY_S) -> str:
    """Best-effort post-click check. Returns an advisory string or "".

    Only a11y and OCR sources are checked. Any error degrades to "".
    """
    if result is None or result.source not in ("a11y", "ocr"):
        return ""
    try:
        time.sleep(delay_s)
        if result.source == "a11y":
            return _verify_a11y(result)
        return _verify_ocr(result)
    except Exception as e:
        logger.debug("verify_after_click failed: %s", e)
        return ""