"""Voice-action module for the Lucas Notes system.

Provides create/read/update/delete/search/stats operations for
notes and notebooks backed by local JSON files.
"""

from __future__ import annotations

from core.logger import get_logger
from core import notes_core as nc

logger = get_logger(__name__)

TOOL_SCHEMA: dict = {
    "name": "notes_control",
    "description": (
        "Manage notes and notebooks. Create, list, view, update, delete, and "
        "search notes. Organize notes into notebooks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Operation: create_notebook, list_notebooks, delete_notebook, "
                    "create_note, list_notes, get_note, update_note, delete_note, "
                    "search_notes, notes_stats, or help"
                ),
            },
            "name": {
                "type": "STRING",
                "description": "Name for a new notebook (used with create_notebook)",
            },
            "description": {
                "type": "STRING",
                "description": "Optional description for a notebook",
            },
            "notebook_id": {
                "type": "STRING",
                "description": "Notebook ID (e.g. nb-1) to filter by",
            },
            "title": {
                "type": "STRING",
                "description": "Note title (used with create_note, update_note)",
            },
            "content": {
                "type": "STRING",
                "description": "Note body content",
            },
            "note_id": {
                "type": "STRING",
                "description": "Note ID (e.g. note-1) for get/update/delete operations",
            },
            "query": {
                "type": "STRING",
                "description": "Search term for search_notes",
            },
        },
        "required": ["action"],
    },
}


def _dispatch(action: str, args: dict) -> str:
    """Route action string to the correct notes_core function."""
    action_map = {
        "create_notebook": lambda: nc.create_notebook(
            name=args.get("name", ""),
            description=args.get("description", ""),
        ),
        "list_notebooks": lambda: nc.list_notebooks(),
        "delete_notebook": lambda: nc.delete_notebook(
            notebook_id=args.get("notebook_id", ""),
        ),
        "create_note": lambda: nc.create_note(
            title=args.get("title", ""),
            content=args.get("content", ""),
            notebook_id=args.get("notebook_id", ""),
        ),
        "list_notes": lambda: nc.list_notes(
            notebook_id=args.get("notebook_id", ""),
        ),
        "get_note": lambda: nc.get_note(
            note_id=args.get("note_id", ""),
        ),
        "update_note": lambda: nc.update_note(
            note_id=args.get("note_id", ""),
            title=args.get("title", ""),
            content=args.get("content", ""),
        ),
        "delete_note": lambda: nc.delete_note(
            note_id=args.get("note_id", ""),
        ),
        "search_notes": lambda: nc.search_notes(
            query=args.get("query", ""),
        ),
        "notes_stats": lambda: nc.notes_stats(),
        "help": lambda: _help_text(),
    }

    handler = action_map.get(action)
    if handler is None:
        valid = ", ".join(sorted(action_map))
        return f"Unknown action: '{action}'. Valid actions: {valid}"
    return handler()


def _help_text() -> str:
    return (
        "Notes Control — manage your personal notes.\n\n"
        "Actions:\n"
        "  create_notebook name=<name> [description=<text>]\n"
        "  list_notebooks\n"
        "  delete_notebook notebook_id=<id>\n"
        "  create_note title=<title> [content=<text>] [notebook_id=<id>]\n"
        "  list_notes [notebook_id=<id>]\n"
        "  get_note note_id=<id>\n"
        "  update_note note_id=<id> [title=<new>] [content=<new>]\n"
        "  delete_note note_id=<id>\n"
        "  search_notes query=<search term>\n"
        "  notes_stats\n"
        "  help"
    )


def notes_control(parameters: dict, player=None, speak: callable = None) -> str:  # type: ignore[type-arg]
    """Execute notes_control action and return a result string."""
    action = parameters.get("action", "").strip().lower()
    if not action:
        return "Missing required parameter: action."

    return _dispatch(action, parameters)
