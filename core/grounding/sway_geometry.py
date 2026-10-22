"""Sway window geometry lookup.

Under Wayland, AT-SPI extents are surface-relative, so global coordinates are
composed from the sway window rect (matched by process pid or title) plus the
element's window-relative extents.
"""

from __future__ import annotations

import json
import subprocess

from core.logger import get_logger
from core.window_list import _session_env, _which

logger = get_logger(__name__)

_GET_TREE_TIMEOUT = 10


def _find_node_with_pid(node: dict, pid: int) -> dict | None:
    if node.get("pid") == pid:
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        found = _find_node_with_pid(child, pid)
        if found is not None:
            return found
    return None


def _get_tree() -> dict | None:
    if not _which("swaymsg"):
        return None
    try:
        p = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            capture_output=True,
            text=True,
            timeout=_GET_TREE_TIMEOUT,
            errors="replace",
            env=_session_env(),
        )
        if p.returncode != 0 or not p.stdout:
            return None
        return json.loads(p.stdout)
    except Exception as e:
        logger.debug("swaymsg get_tree failed: %s", e)
        return None


def swaymsg_window_rect(pid: int) -> tuple[int, int, int, int] | None:
    """Return (x, y, width, height) of the sway window owning *pid*."""
    tree = _get_tree()
    if tree is None:
        return None
    win = _find_node_with_pid(tree, pid)
    if win is None:
        return None
    rect = win.get("rect") or {}
    x = int(rect.get("x", 0))
    y = int(rect.get("y", 0))
    w = int(rect.get("width", 0))
    h = int(rect.get("height", 0))
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def window_rect_for_hint(window_hint: str) -> tuple[int, int, int, int] | None:
    """Find a sway window rect by matching its title/app_id against a hint."""
    tree = _get_tree()
    if tree is None or not window_hint:
        return None
    hint = window_hint.strip().lower()
    stack: list[dict] = [tree]
    while stack:
        node = stack.pop()
        node_name = (node.get("name") or "").lower()
        node_app = (node.get("app_id") or node.get("shell") or "").lower()
        if hint and (hint in node_name or hint in node_app):
            rect = node.get("rect") or {}
            w = int(rect.get("width", 0))
            h = int(rect.get("height", 0))
            if w > 0 and h > 0:
                return int(rect.get("x", 0)), int(rect.get("y", 0)), w, h
        stack.extend(node.get("nodes", []) + node.get("floating_nodes", []))
    return None
