"""Targeted vision-crop grounding.

As a last resort, crops a <=1024px native-resolution region (cursor-centered
or window rect) and asks gemini-3.1-flash-lite-preview for the element location. The
reply parser is strict: only CENTER x y, POINT x y, or NOT_FOUND are accepted;
anything else is retried (up to max_calls) and then treated as not found.

This is the only network path in the grounding router.
"""

from __future__ import annotations

import io
import re

from core.logger import get_logger

logger = get_logger(__name__)

try:
    from google import genai
    from google.genai import types as gtypes

    _GENAI = True
except Exception:
    _GENAI = False

try:
    from PIL import Image  # noqa: F401  (re-exported capability flag)

    _PIL = True
except Exception:
    _PIL = False

from memory.config_manager import get_gemini_key  # noqa: E402  (after guards)
from .capture import capture_region, screen_size  # noqa: E402  (after guards)

_VISION_MODEL = "gemini-3.1-flash-lite-preview"
_CROP_MAX = 1024
_VISION_MAX_CALLS = 3

_REPLY_RE = re.compile(r"^(CENTER|POINT)\s+(\d+)\s+(\d+)\s*$", re.IGNORECASE)


def _parse_vision_reply(text: str) -> tuple[str, int, int] | None:
    """Strictly parse a vision reply. Returns (kind, x, y) or None if malformed."""
    if text is None:
        return None
    raw = text.strip()
    if raw.upper() == "NOT_FOUND":
        return ("NOT_FOUND", 0, 0)
    match = _REPLY_RE.match(raw)
    if match is None:
        return None
    return match.group(1).upper(), int(match.group(2)), int(match.group(3))


def _choose_crop(
    window_rect: tuple[int, int, int, int] | None,
    cursor_center: tuple[int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Return a clamped (left, top, width, height) crop box <= 1024 per side."""
    size = screen_size()
    if size is None:
        sw, sh = 1920, 1080
    else:
        sw, sh = size
    side = min(_CROP_MAX, sw, sh)

    if window_rect is not None:
        wx, wy, ww, wh = window_rect
        return wx, wy, min(ww, _CROP_MAX), min(wh, _CROP_MAX)
    if cursor_center is not None:
        cx, cy = cursor_center
        left = cx - side // 2
        top = cy - side // 2
        return left, top, side, side
    return sw // 2 - side // 2, sh // 2 - side // 2, side, side


def vision_locate(
    target: str,
    *,
    window_rect: tuple[int, int, int, int] | None = None,
    cursor_center: tuple[int, int] | None = None,
    max_calls: int = _VISION_MAX_CALLS,
) -> tuple[int, int] | None:
    """Locate *target* via a vision model on a targeted crop.

    Returns global screen coordinates or None. Prompts are one-shot and
    bounded to *max_calls*; malformed or out-of-bounds replies are retried.
    """
    if not (_GENAI and _PIL):
        return None
    key = get_gemini_key()
    if not key:
        return None
    target = (target or "").strip()
    if not target:
        return None

    box = _choose_crop(window_rect=window_rect, cursor_center=cursor_center)
    if box is None:
        return None
    captured = capture_region(box)
    if captured is None:
        return None
    img, origin_x, origin_y = captured
    w, h = img.size

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    prompt = (
        f"This is a native-resolution screenshot crop of {w}x{h} pixels. "
        f"Locate the UI element described as: '{target}'. "
        f"Reply with ONLY one line: 'CENTER x y' or 'POINT x y' "
        f"(x,y are 0-based pixel coordinates inside this image, within {w}x{h}) "
        f"if found, or exactly 'NOT_FOUND' if not visible. No other text."
    )

    try:
        client = genai.Client(api_key=key)
        for _ in range(max_calls):
            response = client.models.generate_content(
                model=_VISION_MODEL,
                contents=[
                    gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    prompt,
                ],
            )
            reply = (response.text or "").strip()
            parsed = _parse_vision_reply(reply)
            if parsed is None:
                # Malformed reply — retry.
                continue
            kind, cx, cy = parsed
            if kind == "NOT_FOUND":
                return None
            if 0 <= cx < w and 0 <= cy < h:
                return origin_x + cx, origin_y + cy
            # Out-of-bounds coords — treat as malformed, retry.
    except Exception as e:
        logger.warning("vision_locate failed: %s", e)
    return None