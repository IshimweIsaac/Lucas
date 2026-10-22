"""Resolve and list real filesystem paths (anti-hallucination)."""

from __future__ import annotations

from core.path_utils import known_paths, resolve_user_path

TOOL_SCHEMA = {
    "name": "path_helper",
    "description": (
        "Resolve a path to its real on-disk location (Linux paths are case-sensitive). "
        "Use BEFORE read/write/coding when unsure of the exact path. "
        "action=known lists registered projects and pinned workspaces."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "resolve | known",
            },
            "path": {
                "type": "STRING",
                "description": "Path or shortcut (documents, lucas, project registry name).",
            },
        },
        "required": ["action"],
    },
}


def path_helper(*, parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    action = (p.get("action") or "resolve").lower().strip()

    if action == "known":
        paths = known_paths()
        if not paths:
            return "No known paths cached yet. Use file_controller to list directories first."
        lines = ["Known real paths (copy exactly):"]
        for path in paths:
            lines.append(f"  • {path}")
        return "\n".join(lines)

    if action == "resolve":
        raw = (p.get("path") or "").strip()
        if not raw:
            return "❌ path is required for action=resolve."
        res = resolve_user_path(raw, must_exist=True)
        if res.ok:
            if res.corrected:
                return (
                    f"✅ {res.path}\n"
                    f"(You asked for: {res.requested} — using on-disk spelling, "
                    "folder was not renamed.)"
                )
            return f"✅ {res.path}"
        return f"❌ {res.message}"

    return "Unknown action. Use resolve or known."
