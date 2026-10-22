"""Grounding router: resolve a UI element description to screen coordinates.

Resolution order: a11y tree -> OCR -> template -> vision crop. Every layer
clamps to screen bounds. The router also implements the destructive-action
confirmation handshake (two-call, TTL 60s) and post-click verification.

The vision layer is the only network path; total resolution is bounded to
15 seconds.
"""

from __future__ import annotations

import time

from core.logger import get_logger

from . import atspi_tree, capture, ocr_grounding, template_grounding, vision_crop
from .confirms import confirm_required, is_destructive
from .models import SOURCE_A11Y, SOURCE_NONE, SOURCE_OCR, SOURCE_TEMPLATE, SOURCE_VISION
from .models import GroundingResult
from .sway_geometry import window_rect_for_hint
from .verify import clamp, verify_after_click

logger = get_logger(__name__)

try:
    import pyautogui

    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False

_RESOLUTION_TIMEOUT_SEC = 15.0
_A11Y_BUDGET_SEC = 3.0
_OCR_BUDGET_SEC = 3.0
_DEFAULT_RETRIES = 2
_DEFAULT_RETRY_DELAY = 1.0


def _screen_dims() -> tuple[int, int]:
    size = capture.screen_size()
    if size is None:
        return 1920, 1080
    return size


def _run_layer(fn, deadline: float, budget_sec: float, max_retries: int, retry_delay_s: float):
    """Run a grounding layer with retries, bounded by deadline and budget."""
    layer_deadline = min(deadline, time.monotonic() + budget_sec)
    attempts = 0
    while time.monotonic() < layer_deadline:
        try:
            out = fn()
        except Exception as e:
            logger.warning("grounding layer failed: %s", e)
            out = None
        if out is not None:
            return out
        attempts += 1
        if attempts > max_retries:
            break
        if time.monotonic() + retry_delay_s < layer_deadline:
            time.sleep(retry_delay_s)
    return None


def _make_result(res) -> GroundingResult:
    x, y, source, confidence, label = res
    return GroundingResult(
        found=True, source=source, x=x, y=y, confidence=confidence, label=label
    )


def resolve_intent(
    target: str,
    *,
    role: str | None = None,
    window_hint: str | None = None,
    max_retries: int = _DEFAULT_RETRIES,
    retry_delay_s: float = _DEFAULT_RETRY_DELAY,
) -> GroundingResult:
    """Resolve *target* to screen coordinates through the layer cascade."""
    t = (target or "").strip()
    if not t:
        return GroundingResult(found=False, source=SOURCE_NONE, note="no target text")

    deadline = time.monotonic() + _RESOLUTION_TIMEOUT_SEC
    notes: list[str] = []
    sw, sh = _screen_dims()
    img_holder: list[object | None] = [None]

    def ensure_image():
        if img_holder[0] is None:
            cap = capture.capture_screen()
            if cap is not None:
                img_holder[0] = cap[0]
        return img_holder[0]

    # Layer 1: AT-SPI a11y tree
    if atspi_tree.a11y_available():

        def a11y_fn():
            node = atspi_tree.find_node(t, role=role, window_hint=window_hint)
            if node is None:
                return None
            center = atspi_tree.node_global_center(node)
            if center is None:
                return None
            x, y = clamp(center[0], center[1], sw, sh)
            return x, y, SOURCE_A11Y, 1.0, t

        res = _run_layer(a11y_fn, deadline, _A11Y_BUDGET_SEC, max_retries, retry_delay_s)
        if res is not None:
            return _make_result(res)
        notes.append("a11y miss")
    else:
        notes.append("a11y unavailable")

    # Layer 2: OCR
    if ocr_grounding.ocr_available():

        def ocr_fn():
            img = ensure_image()
            if img is None:
                return None
            words = ocr_grounding.ocr_words(img)
            box = ocr_grounding.match_words(words, t)
            if box is None:
                return None
            x, y = clamp(box.cx, box.cy, sw, sh)
            return x, y, SOURCE_OCR, box.conf, box.text

        res = _run_layer(ocr_fn, deadline, _OCR_BUDGET_SEC, max_retries, retry_delay_s)
        if res is not None:
            return _make_result(res)
        notes.append("ocr miss")
    else:
        notes.append("ocr unavailable")

    # Layer 3: template match
    if template_grounding.template_available():

        def template_fn():
            img = ensure_image()
            if img is None:
                return None
            match = template_grounding.template_match(img, t)
            if match is None:
                return None
            score, cx, cy = match
            x, y = clamp(cx, cy, sw, sh)
            return x, y, SOURCE_TEMPLATE, score, t

        res = _run_layer(template_fn, deadline, _RESOLUTION_TIMEOUT_SEC, max_retries, retry_delay_s)
        if res is not None:
            return _make_result(res)
        notes.append("template miss")
    else:
        notes.append("template unavailable")

    # Layer 4: vision crop (only network path)
    if vision_crop._GENAI:
        from memory.config_manager import get_gemini_key

        if get_gemini_key():

            def vision_fn():
                win_rect = None
                if window_hint:
                    win_rect = window_rect_for_hint(window_hint)
                loc = vision_crop.vision_locate(t, window_rect=win_rect, max_calls=3)
                if loc is None:
                    return None
                x, y = clamp(loc[0], loc[1], sw, sh)
                return x, y, SOURCE_VISION, 0.9, t

            res = _run_layer(vision_fn, deadline, _RESOLUTION_TIMEOUT_SEC, max_retries, retry_delay_s)
            if res is not None:
                return _make_result(res)
            notes.append("vision miss")
        else:
            notes.append("vision skipped (no key)")
    else:
        notes.append("vision unavailable")

    if time.monotonic() >= deadline:
        notes.append("timeout")
    return GroundingResult(
        found=False, source=SOURCE_NONE, note="; ".join(notes) or "all layers missed"
    )


def _default_click(x: int, y: int) -> None:
    if not _PYAUTOGUI:
        raise RuntimeError("pyautogui unavailable for click injection")
    pyautogui.click(x, y)


def router_click(
    target: str,
    *,
    role: str | None = None,
    window_hint: str | None = None,
    max_retries: int = _DEFAULT_RETRIES,
    retry_delay_s: float = _DEFAULT_RETRY_DELAY,
    click_fn=None,
    verify: bool = True,
) -> str:
    """Resolve *target* and click it, with confirmation for destructive targets.

    Returns the tool result string. click_fn(x, y) defaults to a guarded
    pyautogui click; callers (computer_control) pass their own injector.
    """
    t = (target or "").strip()
    if not t:
        return "Element not found on screen: ''"

    if is_destructive(t) and confirm_required(t):
        return (
            f"CONFIRM_REQUIRED: '{t}' — ask the user to confirm, "
            "then call screen_click again with the same description."
        )

    result = resolve_intent(
        t, role=role, window_hint=window_hint,
        max_retries=max_retries, retry_delay_s=retry_delay_s,
    )
    if not result.found:
        return f"Element not found on screen: '{t}'"

    try:
        if click_fn is not None:
            click_fn(result.x, result.y)
        else:
            _default_click(result.x, result.y)
    except Exception as e:
        logger.warning("router_click injection failed: %s", e)
        return f"click failed: {e}"

    base = f"Clicked '{t}' at ({result.x},{result.y}) via {result.source}"
    if verify and result.source in (SOURCE_A11Y, SOURCE_OCR):
        advisory = verify_after_click(result, delay_s=0.8)
        if advisory:
            return base + f" click injected but post-verify could not confirm '{t}' (verify: {advisory})"
    return base
