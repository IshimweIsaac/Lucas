"""
Tool Registry — single source of truth for LUCAS tool schemas and dispatch.

Every action module registers itself by exposing:
  TOOL_SCHEMA   – Gemini function-declaration dict
  <handler_fn>  – the callable that executes the tool

The registry is populated at import time via `_auto_register()`.
"""

from __future__ import annotations

import importlib
import re
import threading
from typing import Callable

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)
_REGISTRY_FILE = get_base_dir() / "agent" / "tool_registry.py"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


# ---------------------------------------------------------------------------
# Registry data
# ---------------------------------------------------------------------------
_TOOL_MAP: dict[
    str, dict
] = {}  # name → {"schema": dict, "handler": callable, "accepts_speak": bool}
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def register(
    name: str, schema: dict, handler: Callable, *, accepts_speak: bool = False
) -> None:
    """Register a tool. Always overwrites if *name* already exists (idempotent)."""
    with _lock:
        _TOOL_MAP[name] = {
            "schema": schema,
            "handler": handler,
            "accepts_speak": accepts_speak,
        }


def get_schemas() -> list[dict]:
    """Return all registered tool schemas for Gemini function declarations."""
    with _lock:
        return [entry["schema"] for entry in _TOOL_MAP.values()]


def dispatch(
    name: str, parameters: dict, *, player=None, speak: Callable | None = None
) -> str:
    """Look up *name* and call the handler, returning its string result."""
    with _lock:
        entry = _TOOL_MAP.get(name)

    if entry is None:
        raise KeyError(f"Unknown tool: {name}")

    handler = entry["handler"]
    accepts_speak = entry["accepts_speak"]

    kwargs: dict = {"parameters": parameters, "player": player}
    if accepts_speak:
        kwargs["speak"] = speak

    result = handler(**kwargs)
    return result or "Done."


def is_registered(name: str) -> bool:
    with _lock:
        return name in _TOOL_MAP


def has_tool(name: str) -> bool:
    """Alias for is_registered (used by main.py and executor)."""
    return is_registered(name)


def list_tool_names() -> list[str]:
    with _lock:
        return sorted(_TOOL_MAP.keys())


def register_module(
    module_path: str,
    func_name: str,
    *,
    accepts_speak: bool = False,
) -> str:
    """Import (or reload) an action module and register it at runtime."""
    if not _NAME_RE.match(func_name):
        raise ValueError(f"Invalid tool function name: {func_name}")

    mod = importlib.import_module(module_path)
    mod = importlib.reload(mod)
    schema = getattr(mod, "TOOL_SCHEMA", None)
    handler = getattr(mod, func_name, None)
    if schema is None or handler is None:
        raise ValueError(f"{module_path} missing TOOL_SCHEMA or {func_name}")

    register(
        name=schema["name"],
        schema=schema,
        handler=handler,
        accepts_speak=accepts_speak,
    )
    return schema["name"]


def ensure_action_module_entry(
    module_path: str,
    func_name: str,
    accepts_speak: bool,
) -> bool:
    """Append module to _ACTION_MODULES in tool_registry.py if missing."""
    text = _REGISTRY_FILE.read_text(encoding="utf-8")
    if f'"{module_path}"' in text:
        return False

    line = f'    ("{module_path}", "{func_name}", {accepts_speak}),'
    marker = "\n]\n\n\ndef _auto_register"
    if marker not in text:
        raise RuntimeError("Could not find _ACTION_MODULES block in tool_registry.py")
    text = text.replace(marker, f"\n{line}{marker}", 1)
    _REGISTRY_FILE.write_text(text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Auto-registration of all action modules
# ---------------------------------------------------------------------------

# Each tuple: (module_path, function_name, accepts_speak)
_ACTION_MODULES = [
    ("actions.open_app", "open_app", False),
    ("actions.web_search", "web_search", False),
    ("actions.browser_control", "browser_control", False),
    ("actions.path_helper", "path_helper", False),
    ("actions.file_controller", "file_controller", False),
    ("actions.coding_workspace", "coding_workspace", True),
    ("actions.self_improve", "self_improve", True),
    ("actions.tool_builder", "tool_builder", True),
    ("actions.screen_processor", "screen_process", False),
    ("actions.send_message", "send_message", False),
    ("actions.reminder", "reminder", False),
    ("actions.weather_report", "weather_action", False),
    ("actions.computer_settings", "computer_settings", False),
    ("actions.computer_control", "computer_control", False),
    ("actions.file_processor", "file_processor", True),
    ("actions.calendar_manager", "manage_calendar", False),
    ("actions.heartbeat", "heartbeat_control", False),
    ("actions.lucas_service", "lucas_service", False),
    ("actions.pc_controller", "pc_controller", False),
    ("actions.sway_control", "sway_control", False),
    ("actions.system_control", "system_control", False),
    ("actions.context_agent", "context_agent", False),
    ("actions.notes_control", "notes_control", False),
    ("actions.email_control", "email_control", False),
    ("actions.opencode_control", "opencode_control", True),  # accepts_speak=True
    ("actions.lpm_control", "lpm_control", False),
    ("actions.habits_control", "habits_control", False),
    ("actions.presentation_control", "presentation_control", False),
    ("actions.proactive", "proactive", False),
    ("actions.memory_recall", "memory_recall", False),
    ("actions.openrouter_control", "openrouter_control", False),
]


def _auto_register() -> None:
    """Import every action module and register its TOOL_SCHEMA + handler."""
    for module_path, func_name, accepts_speak in _ACTION_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            logger.warning(f"[ToolRegistry] ⚠️  Could not import {module_path}: {exc}")
            continue

        schema = getattr(mod, "TOOL_SCHEMA", None)
        handler = getattr(mod, func_name, None)

        if schema is None:
            logger.warning(
                f"[ToolRegistry] ⚠️  {module_path} has no TOOL_SCHEMA — skipping"
            )
            continue
        if handler is None:
            logger.warning(
                f"[ToolRegistry] ⚠️  {module_path} has no function '{func_name}' — skipping"
            )
            continue

        register(
            name=schema["name"],
            schema=schema,
            handler=handler,
            accepts_speak=accepts_speak,
        )

    try:
        from memory.custom_tools.loader import register_custom_tools

        custom = register_custom_tools(register)
        if custom:
            logger.info(f"[ToolRegistry] ✅ Custom tools: {', '.join(custom)}")
    except Exception as exc:
        logger.warning(f"[ToolRegistry] ⚠️ Custom tools: {exc}")

    logger.info(f"[ToolRegistry] ✅ Registered {len(_TOOL_MAP)} tools")


# Run auto-registration on first import
_auto_register()
