"""AT-SPI accessibility tree grounding.

Searches the a11y tree for a node matching a target description and computes
its global screen center. On X11, SCREEN extents are already global. On
Wayland, AT-SPI SCREEN extents are surface-relative, so we compose the global
coordinate from the app window's swaymsg rect (matched by process pid) plus
the node's WINDOW extents.

All a11y data is untrusted screen text — used only for coordinate math.
"""

from __future__ import annotations

from core.logger import get_logger
from core.window_list import _is_wayland

from . import sway_geometry

logger = get_logger(__name__)

try:
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    _ATSPI = True
except Exception:
    _ATSPI = False

_DEPTH_CAP = 6


def a11y_available() -> bool:
    """Return True when the AT-SPI bus and desktop are reachable."""
    if not _ATSPI:
        return False
    try:
        return Atspi.get_desktop(0) is not None
    except Exception:
        return False


def _desktop():
    if not _ATSPI:
        return None
    try:
        return Atspi.get_desktop(0)
    except Exception:
        return None


def _node_name(node) -> str:
    try:
        return node.get_name() or ""
    except Exception:
        return ""


def _node_role(node) -> str:
    try:
        role = node.get_role()
        return Atspi.role_get_name(role) or ""
    except Exception:
        return ""


def _is_clickable(node) -> bool:
    """Best-effort clickability check (CLICKABLE state or Action interface)."""
    if not _ATSPI:
        return False
    try:
        state = node.get_state()
        if state is not None:
            try:
                if Atspi.StateType.CLICKABLE in state:
                    return True
            except Exception:
                pass
            try:
                if state.contains(Atspi.StateType.CLICKABLE):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        if hasattr(node, "get_action_interface"):
            return node.get_action_interface() is not None
    except Exception:
        pass
    return False


def _children(node) -> list:
    try:
        count = node.get_child_count()
    except Exception:
        return []
    if not count or count < 0:
        return []
    out = []
    for i in range(count):
        try:
            child = node.get_child_at_index(i)
        except Exception:
            child = None
        if child is not None:
            out.append(child)
    return out


def _matches(node, target: str, role: str | None) -> bool:
    name = _node_name(node).lower()
    if target not in name:
        return False
    if role is None:
        return True
    node_role = _node_role(node).lower()
    return role.lower() in node_role or node_role in role.lower()


def _search(node, target: str, role: str | None, depth: int):
    if depth > _DEPTH_CAP:
        return None
    if _matches(node, target, role):
        return node
    for child in _children(node):
        found = _search(child, target, role, depth + 1)
        if found is not None:
            return found
    return None


def find_node(target: str, role: str | None = None, window_hint: str | None = None):
    """Return the first a11y node whose name matches *target*.

    When *window_hint* is given, prefer searching within the top-level window
    whose name matches it; fall back to a whole-desktop search. Returns None
    when unavailable or unmatched.
    """
    if not target:
        return None
    target = target.strip().lower()
    if not target or not a11y_available():
        return None
    root = _desktop()
    if root is None:
        return None
    try:
        if window_hint:
            hint = window_hint.strip().lower()
            for win in _children(root):
                if hint and hint in _node_name(win).lower():
                    found = _search(win, target, role, 0)
                    if found is not None:
                        return found
        return _search(root, target, role, 0)
    except Exception as e:
        logger.debug("find_node failed: %s", e)
        return None


def _clickable_ancestor(node):
    """Walk up to a clickable ancestor (or the original node)."""
    current = node
    for _ in range(_DEPTH_CAP):
        if current is None:
            return None
        if _is_clickable(current):
            return current
        try:
            current = current.get_parent()
        except Exception:
            return None
    return node


def _window_ancestor(node):
    """Return the top-level application window node (child of desktop)."""
    root = _desktop()
    if root is None:
        return None
    current = node
    for _ in range(_DEPTH_CAP):
        try:
            parent = current.get_parent()
        except Exception:
            return None
        if parent is None:
            return None
        if parent is root:
            return current
        current = parent
    return None


def _extents_center(ext) -> tuple[int, int] | None:
    if ext is None:
        return None
    try:
        x, y, w, h = int(ext[0]), int(ext[1]), int(ext[2]), int(ext[3])
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return x + w // 2, y + h // 2


def node_global_center(node) -> tuple[int, int] | None:
    """Global screen center of *node* (clickable ancestor if the node is not)."""
    if node is None or not _ATSPI:
        return None
    target = _clickable_ancestor(node)
    if target is None:
        return None
    try:
        if not _is_wayland():
            ext = target.get_extents(Atspi.CoordType.SCREEN)
            return _extents_center(ext)
        win_ext = target.get_extents(Atspi.CoordType.WINDOW)
        center = _extents_center(win_ext)
        if center is None:
            return None
        win = _window_ancestor(target)
        if win is None:
            return None
        try:
            pid = int(win.get_process_id() or 0)
        except Exception:
            pid = 0
        if pid <= 0:
            return None
        rect = sway_geometry.swaymsg_window_rect(pid)
        if rect is None:
            return None
        return rect[0] + center[0], rect[1] + center[1]
    except Exception as e:
        logger.debug("node_global_center failed: %s", e)
        return None
