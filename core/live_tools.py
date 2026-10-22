"""Trim tool declarations for Gemini Live API — prevents 1008 payload errors."""

from __future__ import annotations

from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)

# Size limits
_MAX_TOOL_DESC: int = 400       # max chars for top-level tool description
_MAX_PROP_DESC: int = 140       # max chars for each property description
_MAX_PROPERTIES: int = 28       # max properties per tool (trims to keep the most important)
_MAX_TOOLS: int = 20            # max tools to send in one declaration (priority-ordered)

# Priority tool names (keep these FIRST, trim the rest)
_PRIORITY_TOOLS: frozenset[str] = frozenset({
    # Core conversation tools
    "pc_controller",
    "computer_control",
    "computer_settings",
    "web_search",
    "browser_control",
    # Heavy tools (most used)
    "system_control",
    "plane_control",
    "context_agent",
    "opencode_control",
    "coding_workspace",
    "file_controller",
    "screen_process",
    # Other essential
    "open_app",
    "calendar_manager",
    "reminder",
})


def trim_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Trim a single tool schema to fit Live API limits."""
    trimmed = dict(schema)

    # Trim top-level description
    desc = trimmed.get("description", "")
    if isinstance(desc, str) and len(desc) > _MAX_TOOL_DESC:
        trimmed["description"] = desc[:_MAX_TOOL_DESC] + "\u2026"

    # Trim parameters
    params = trimmed.get("parameters", {})
    if not isinstance(params, dict):
        return trimmed

    props = params.get("properties", {})
    if not isinstance(props, dict):
        return trimmed

    # Trim property descriptions
    for prop_name, prop_schema in props.items():
        if not isinstance(prop_schema, dict):
            continue
        prop_desc = prop_schema.get("description", "")
        if isinstance(prop_desc, str) and len(prop_desc) > _MAX_PROP_DESC:
            prop_schema["description"] = prop_desc[:_MAX_PROP_DESC] + "\u2026"

    # Limit number of properties
    prop_items = list(props.items())
    if len(prop_items) > _MAX_PROPERTIES:
        # Always keep the "action" property first (it's the primary dispatch)
        # then fill up to _MAX_PROPERTIES with remaining properties
        kept: list = []
        seen_action = False
        for k, v in prop_items:
            if k == "action" and not seen_action:
                kept.insert(0, (k, v))
                seen_action = True
            elif len(kept) < _MAX_PROPERTIES:
                kept.append((k, v))
        trimmed["parameters"]["properties"] = dict(kept)

    return trimmed


def trim_tools(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim all tool schemas. Respects priority ordering."""
    # Sort: priority tools first, then others
    def _sort_key(s: dict) -> tuple[int, str]:
        name = s.get("name", "")
        return (0 if name in _PRIORITY_TOOLS else 1, name)

    sorted_schemas = sorted(schemas, key=_sort_key)

    # Trim each schema
    trimmed = [trim_schema(s) for s in sorted_schemas]

    # Limit total number of tools
    if len(trimmed) > _MAX_TOOLS:
        logger.warning(
            "[LiveTools] Trimming %d tools to %d (too many for Live API)",
            len(trimmed), _MAX_TOOLS,
        )
        trimmed = trimmed[:_MAX_TOOLS]

    return trimmed
