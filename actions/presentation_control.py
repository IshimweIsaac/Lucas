"""Lucas Presentation Engine — show rich visual slides on screen.

Creates beautiful dark-themed HTML presentations with embedded CSS.
Supports: title slides, lists, stats dashboards, tables, progress bars,
code blocks, and text slides. Navigate slides with next/prev/close.
"""

from __future__ import annotations

import re
import threading

from core import sway_control as sway
from core.logger import get_logger

logger = get_logger(__name__)

# Registry of open presentation window keys. Action modules are stateless
# across calls, so this module-level state tracks which keys are open and
# which was last opened (for next/prev/close without an explicit window_key).
_open_presentation_keys: set[str] = set()
_last_presentation_key: str = "presentation"
_registry_lock = threading.RLock()

TOOL_SCHEMA = {
    "name": "presentation_control",
    "description": (
        "USE THIS when the user asks me to visually SHOW, DISPLAY, or PRESENT information on the screen. Creates beautiful full-screen HTML slides on the desktop — titles, lists, stats dashboards with cards, tables, progress bars, code blocks, and text slides. Great for showing project dashboards, system status, task lists, code reviews, and visual briefings."
        "title slides, lists, stats dashboards, tables, progress bars, "
        "code blocks. Lucas can create rich visual presentations from "
        "any data: projects, notes, habits, system status, etc."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "show_title | show_list | show_stats | show_table | "
                    "show_progress | show_code | show_text | "
                    "next_slide | prev_slide | close_presentation"
                ),
            },
            "title": {"type": "STRING", "description": "Slide or presentation title"},
            "subtitle": {"type": "STRING", "description": "Subtitle for title slide"},
            "items": {
                "type": "STRING",
                "description": "Comma-separated list items for list slide",
            },
            "headers": {
                "type": "STRING",
                "description": "Comma-separated column headers for table",
            },
            "rows": {
                "type": "STRING",
                "description": (
                    "Row data for tables (semicolon-separated rows, "
                    "comma-separated columns)"
                ),
            },
            "body": {"type": "STRING", "description": "Text body for text slide"},
            "code": {
                "type": "STRING",
                "description": "Code content for code slide",
            },
            "labels_values": {
                "type": "STRING",
                "description": (
                    "For progress/stats: label:value pairs separated by "
                    "semicolons (e.g. 'Coding:70;Design:30')"
                ),
            },
            "presentation_title": {
                "type": "STRING",
                "description": "Title for multi-slide presentation (default: 'Briefing')",
            },
            "window_key": {
                "type": "STRING",
                "description": (
                    "Optional window key for this presentation window. "
                    "Reusing the same key replaces that window."
                ),
            },
            "workspace": {
                "type": "INTEGER",
                "description": (
                    "Optional Sway workspace number (>= 1) to switch to "
                    "before showing the presentation"
                ),
            },
        },
        "required": ["action"],
    },
}


def _slugify_key(title: str) -> str:
    """Turn *title* into a safe window-key fragment.

    Lowercases, collapses non-alphanumeric runs to a single '-', strips
    edge separators, truncates to ~40 chars. Returns "" when nothing
    usable remains.
    """
    if not title:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:40].rstrip("-")


def _derive_window_key(parameters: dict) -> str:
    """Compute the base window key for a show_* action.

    Priority: explicit window_key (slugified) > presentation_title/title
    (slugified) > "presentation".
    """
    explicit = (parameters.get("window_key") or "").strip()
    if explicit:
        slug = _slugify_key(explicit)
        return f"presentation:{slug}" if slug else "presentation"
    title = (
        parameters.get("presentation_title") or parameters.get("title") or ""
    ).strip()
    slug = _slugify_key(title)
    return f"presentation:{slug}" if slug else "presentation"


def _reserve_window_key(base: str, *, replace: bool = False) -> str:
    """Reserve *base* in the open-keys registry; dedupe with -2/-3 when needed.

    replace=True (explicit window_key) reuses the same key instead of
    creating -2, so a re-open replaces the existing window.
    """
    global _last_presentation_key
    with _registry_lock:
        if replace:
            _open_presentation_keys.discard(base)
            _open_presentation_keys.add(base)
        elif base in _open_presentation_keys:
            i = 2
            while f"{base}-{i}" in _open_presentation_keys:
                i += 1
            base = f"{base}-{i}"
            _open_presentation_keys.add(base)
        else:
            _open_presentation_keys.add(base)
        _last_presentation_key = base
        return base


def _show_window_key(parameters: dict) -> str:
    """Derive and reserve the window key for a show_* action."""
    return _reserve_window_key(_derive_window_key(parameters), replace=bool(
        (parameters.get("window_key") or "").strip()
    ))


def _resolve_nav_key(parameters: dict) -> str:
    """Window key for nav/close: explicit window_key or the last opened key."""
    explicit = (parameters.get("window_key") or "").strip()
    if explicit:
        slug = _slugify_key(explicit)
        return f"presentation:{slug}" if slug else "presentation"
    return _last_presentation_key


def _switch_workspace_if_requested(parameters: dict) -> str:
    """Best-effort Sway workspace switch before opening a presentation.

    Safe-fails: a missing/invalid workspace param never raises, so the
    presentation still opens on the current workspace.
    """
    ws = parameters.get("workspace")
    if ws is None:
        return ""
    try:
        n = int(ws)
    except (TypeError, ValueError):
        return f"Invalid workspace: {ws!r} ignored."
    if n < 1:
        return f"Invalid workspace: {n} ignored (use >= 1)."
    try:
        return sway.switch_workspace(n)
    except Exception as exc:
        logger.warning("Workspace switch failed: %s", exc)
        return f"Workspace switch failed: {exc}"


def _show_presentation(
    player, presentation: dict, window_key: str = "presentation"
) -> None:
    """Send presentation to the UI via WebSocket, targeting *window_key*."""
    try:
        if player is not None and hasattr(player, "open_presentation_slides"):
            player.open_presentation_slides(presentation, window=window_key)
    except Exception as exc:
        logger.warning("Failed to show presentation: %s", exc)


def _parse_labels_values(raw: str) -> list[tuple[str, str]]:
    """Parse a 'label:value;label:value' string into list of (label, value) tuples."""
    result: list[tuple[str, str]] = []
    if not raw:
        return result
    for pair in raw.split(";"):
        pair = pair.strip()
        if ":" in pair:
            parts = pair.split(":", 1)
            result.append((parts[0].strip(), parts[1].strip()))
        elif pair:
            result.append((pair, ""))
    return result


def presentation_control(parameters: dict, player=None) -> str:
    """Execute a presentation action. Dispatches to slide builders."""
    from core.presentation_core import (
        build_presentation,
        code_slide,
        list_slide,
        progress_slide,
        stats_slide,
        table_slide,
        text_slide,
        title_slide,
    )

    action = (parameters.get("action") or "").lower().strip().replace(" ", "_")
    if not action:
        return "No action specified. Use show_title, show_list, show_stats, etc."

    # ── Show a single slide ──────────────────────────────────────────

    if action == "show_title":
        name = parameters.get("title", "Lucas Presentation")
        sub = parameters.get("subtitle", "")
        slide = title_slide(name, sub)
        pres_title = parameters.get("presentation_title", name)
        pres = build_presentation(pres_title, [slide], ["Title"])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing: {name}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_list":
        title = parameters.get("title", "List")
        items_str = parameters.get("items", "")
        items = [i.strip() for i in items_str.split(",") if i.strip()]
        slide = list_slide(title, items)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing list: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_stats":
        title = parameters.get("title", "Stats")
        raw = parameters.get("labels_values", "")
        stats = _parse_labels_values(raw)
        slide = stats_slide(title, stats)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing stats: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_table":
        title = parameters.get("title", "Table")
        headers_str = parameters.get("headers", "")
        rows_str = parameters.get("rows", "")
        headers = [h.strip() for h in headers_str.split(",") if h.strip()]
        rows: list[list[str]] = []
        for row_str in rows_str.split(";"):
            row_str = row_str.strip()
            if row_str:
                row = [c.strip() for c in row_str.split(",")]
                rows.append(row)
        slide = table_slide(title, headers, rows)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing table: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_progress":
        title = parameters.get("title", "Progress")
        raw = parameters.get("labels_values", "")
        items: list[tuple[str, int]] = []
        for pair in raw.split(";"):
            pair = pair.strip()
            if ":" in pair:
                parts = pair.split(":", 1)
                try:
                    items.append((parts[0].strip(), int(parts[1].strip())))
                except ValueError:
                    items.append((parts[0].strip(), 0))
            elif pair:
                items.append((pair, 0))
        slide = progress_slide(title, items)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing progress: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_code":
        title = parameters.get("title", "Code")
        code = parameters.get("code", "")
        slide = code_slide(title, code)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing code: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    if action == "show_text":
        title = parameters.get("title", "Note")
        body = parameters.get("body", "")
        slide = text_slide(title, body)
        pres_title = parameters.get("presentation_title", title)
        pres = build_presentation(pres_title, [slide], [title])
        ws_msg = _switch_workspace_if_requested(parameters)
        window_key = _show_window_key(parameters)
        _show_presentation(player, pres, window_key)
        return f"Showing text: {title}" + (f" [{ws_msg}]" if ws_msg else "")

    # ── Navigation ───────────────────────────────────────────────────

    if action in ("next_slide", "advance"):
        if player is not None and hasattr(player, "advance_presentation_slide"):
            window_key = _resolve_nav_key(parameters)
            return player.advance_presentation_slide(1, window=window_key)
        return "Cannot advance slide — no player available"

    if action in ("prev_slide", "back"):
        if player is not None and hasattr(player, "advance_presentation_slide"):
            window_key = _resolve_nav_key(parameters)
            return player.advance_presentation_slide(-1, window=window_key)
        return "Cannot go back — no player available"

    if action == "close_presentation":
        if player is not None and hasattr(player, "close_presentation"):
            window_key = _resolve_nav_key(parameters)
            with _registry_lock:
                _open_presentation_keys.discard(window_key)
            player.close_presentation(window=window_key)
            return "Presentation closed"
        return "Cannot close presentation — no player available"

    return (
        f"Unknown action: {action}. "
        "Use: show_title, show_list, show_stats, show_table, "
        "show_progress, show_code, show_text, next_slide, "
        "prev_slide, close_presentation."
    )
