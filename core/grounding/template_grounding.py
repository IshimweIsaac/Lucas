"""Template-matching grounding via OpenCV.

Scans core/grounding/templates/*.png for a template whose filename matches the
target, then runs cv2.matchTemplate over the screen image. The layer is inert
when the templates directory is empty or cv2/numpy are unavailable.
"""

from __future__ import annotations

from memory.config_manager import get_base_dir

from core.logger import get_logger

logger = get_logger(__name__)

try:
    import cv2

    _CV2 = True
except Exception:
    _CV2 = False

try:
    import numpy as np

    _NP = True
except Exception:
    _NP = False

_TEMPLATE_DIR = get_base_dir() / "core" / "grounding" / "templates"
_MATCH_THRESHOLD = 0.75


def template_available() -> bool:
    """True when cv2+numpy exist and the templates dir has PNGs."""
    if not (_CV2 and _NP):
        return False
    try:
        return _TEMPLATE_DIR.is_dir() and any(_TEMPLATE_DIR.glob("*.png"))
    except Exception:
        return False


def _normalize_stem(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").lower().strip()


def template_match(image, target: str) -> tuple[float, int, int] | None:
    """Return (score, center_x, center_y) of the best template match or None.

    Templates whose normalized filename is contained in the target (or vice
    versa) are candidates; the best scoring match above the threshold wins.
    """
    if not template_available():
        return None
    target_lower = (target or "").strip().lower()
    if not target_lower:
        return None
    try:
        screen_gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    except Exception as e:
        logger.debug("template_match: convert failed: %s", e)
        return None

    best: tuple[float, int, int] | None = None
    for path in _TEMPLATE_DIR.glob("*.png"):
        stem = _normalize_stem(path.stem)
        if stem not in target_lower and target_lower not in stem:
            continue
        templ = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if templ is None:
            continue
        th, tw = templ.shape[:2]
        sh, sw = screen_gray.shape[:2]
        if th > sh or tw > sw:
            continue
        try:
            res = cv2.matchTemplate(screen_gray, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
        except Exception as e:
            logger.debug("template_match: matchTemplate failed for %s: %s", path.name, e)
            continue
        if max_val >= _MATCH_THRESHOLD:
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            if best is None or max_val > best[0]:
                best = (float(max_val), cx, cy)
    return best