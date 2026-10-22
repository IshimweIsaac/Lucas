"""Screen capture primitives for the grounding router.

Capture order is strict: grim (Wayland) -> mss -> pyautogui. gnome-screenshot
is never used first because it fails under Sway. Window geometry composition
lives in sway_geometry.py.
"""

from __future__ import annotations

import io
import subprocess

from core.logger import get_logger
from core.window_list import _is_wayland, _session_env, _which

logger = get_logger(__name__)

try:
    from PIL import Image

    _PIL = True
except Exception:
    _PIL = False

try:
    import mss

    _MSS = True
except Exception:
    _MSS = False

try:
    import pyautogui

    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False

_GRIM_TIMEOUT = 10


def screen_size() -> tuple[int, int] | None:
    """Return (width, height) of the primary screen, or None if unknown."""
    if _MSS:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                return int(mon["width"]), int(mon["height"])
        except Exception as e:
            logger.debug("screen_size via mss failed: %s", e)
    if _PYAUTOGUI:
        try:
            w, h = pyautogui.size()
            return int(w), int(h)
        except Exception as e:
            logger.debug("screen_size via pyautogui failed: %s", e)
    return None


def _capture_grim() -> tuple[object, int, int] | None:
    if not _is_wayland() or not _which("grim") or not _PIL:
        return None
    try:
        p = subprocess.run(
            ["grim", "-t", "png", "-"],
            capture_output=True,
            env=_session_env(),
            timeout=_GRIM_TIMEOUT,
        )
        if p.returncode != 0 or not p.stdout:
            return None
        img = Image.open(io.BytesIO(p.stdout)).convert("RGB")
        return img, img.width, img.height
    except Exception as e:
        logger.warning("capture grim failed: %s", e)
        return None


def _capture_mss() -> tuple[object, int, int] | None:
    if not _MSS:
        return None
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            target = monitors[1] if len(monitors) > 1 else monitors[0]
            shot = sct.grab(target)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            return img, img.width, img.height
    except Exception as e:
        logger.warning("capture mss failed: %s", e)
        return None


def _capture_pyautogui() -> tuple[object, int, int] | None:
    if not _PYAUTOGUI or not _PIL:
        return None
    try:
        img = pyautogui.screenshot().convert("RGB")
        return img, img.width, img.height
    except Exception as e:
        logger.warning("capture pyautogui failed: %s", e)
        return None


def capture_screen() -> tuple[object, int, int] | None:
    """Capture the full screen. Returns (PIL RGB image, w, h) or None.

    Order: grim (Wayland) -> mss -> pyautogui. Never gnome-screenshot.
    """
    for backend in (_capture_grim, _capture_mss, _capture_pyautogui):
        shot = backend()
        if shot is not None:
            return shot
    return None


def capture_region(box: tuple[int, int, int, int]) -> tuple[object, int, int] | None:
    """Capture a clamped region. box = (left, top, width, height).

    Returns (cropped RGB image, origin_x, origin_y) where origin is the
    global screen coordinate of the crop's top-left corner.
    """
    size = screen_size()
    if size is None:
        return None
    sw, sh = size
    left, top, width, height = box
    right = min(left + width, sw)
    bottom = min(top + height, sh)
    left = max(left, 0)
    top = max(top, 0)
    if right <= left or bottom <= top:
        return None
    shot = capture_screen()
    if shot is None or not _PIL:
        return None
    img = shot[0].crop((left, top, right, bottom)).convert("RGB")
    return img, left, top
