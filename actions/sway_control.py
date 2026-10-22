"""Sway desktop workspace control — voice tool wrapping core.sway_control."""

from __future__ import annotations

from core import sway_control as sway
from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "sway_control",
    "description": (
        "Control Sway desktop workspaces (Wayland) via swaymsg. Switch to a "
        "workspace by number, or list workspaces. Use for 'go to workspace 3', "
        "'switch to desktop 2', 'switch workspace 5', or 'present on workspace 7'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "switch_workspace | list_workspaces",
            },
            "number": {
                "type": "INTEGER",
                "description": "Workspace number to switch to (>= 1)",
            },
        },
        "required": ["action"],
    },
}


def sway_control(*, parameters: dict, player=None, speak=None) -> str:
    """Execute a Sway workspace action."""
    action = (parameters.get("action") or "").lower().strip().replace(" ", "_")

    if action in ("switch_workspace", "switch"):
        number = parameters.get("number")
        if number is None:
            return "Provide number= (workspace number >= 1) for switch_workspace."
        return sway.switch_workspace(number)

    if action in ("list_workspaces", "list"):
        return sway.list_workspaces()

    return (
        f"Unknown action: {action}. "
        "Use switch_workspace or list_workspaces."
    )