"""Sway desktop workspace control — switch/list workspaces via swaymsg."""

from __future__ import annotations

import json
import shutil

from core.logger import get_logger
from core.pc_control import CmdResult, _run

logger = get_logger(__name__)


def swaymsg_available() -> bool:
    """Return True if the swaymsg binary is on PATH."""
    return shutil.which("swaymsg") is not None


def switch_workspace(number: int) -> str:
    """Switch to the Sway workspace *number* (>= 1). Returns a user string."""
    if isinstance(number, bool) or not isinstance(number, (int, str)):
        return f"Invalid workspace number: {number!r}. Use a positive integer."
    try:
        n = int(number)
    except (TypeError, ValueError):
        return f"Invalid workspace number: {number!r}. Use a positive integer."
    if n < 1:
        return f"Invalid workspace number: {n}. Use a positive integer (>= 1)."
    if not swaymsg_available():
        return (
            "swaymsg not found. Install sway (provides /usr/bin/swaymsg) "
            "to switch workspaces."
        )
    r: CmdResult = _run(["swaymsg", "workspace", "number", str(n)])
    if r.ok:
        return f"Switched to workspace {n}."
    return f"Failed to switch to workspace {n}: {r.stderr or r.stdout or 'unknown error'}"


def list_workspaces() -> str:
    """List Sway workspaces, marking the focused one. Returns a user string."""
    if not swaymsg_available():
        return (
            "swaymsg not found. Install sway (provides /usr/bin/swaymsg) "
            "to list workspaces."
        )
    r: CmdResult = _run(["swaymsg", "-t", "get_workspaces"])
    if not r.ok:
        return f"Failed to list workspaces: {r.stderr or r.stdout or 'unknown error'}"
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        logger.warning("swaymsg get_workspaces returned invalid JSON")
        return "Could not parse available workspaces."
    if not isinstance(data, list):
        return "Unexpected swaymsg output."
    if not data:
        return "No workspaces found."
    lines: list[str] = []
    for ws in data:
        num = ws.get("num")
        name = ws.get("name") or ""
        focused = " (focused)" if ws.get("focused") else ""
        lines.append(f"Workspace {num if num is not None else '?'}: {name}{focused}")
    return "\n".join(lines) or "No workspaces found."
