"""Lucas Notes — local JSON-backed note-taking system."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_NOTES_DIR = Path(__file__).resolve().parent.parent / "memory" / "notes"
_NOTES_FILE = _NOTES_DIR / "notes.json"
_NOTEBOOKS_FILE = _NOTES_DIR / "notebooks.json"


def _ensure_dirs() -> None:
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> list | dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []
    return []


def _save_json(path: Path, data: list | dict) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── NOTEBOOKS ──


def create_notebook(name: str, description: str = "") -> str:
    """Create a new notebook and return a result message."""
    notebooks = _load_json(_NOTEBOOKS_FILE)
    nid = f"nb-{len(notebooks) + 1}"
    notebooks.append(
        {
            "id": nid,
            "name": name,
            "description": description,
            "created": datetime.now().isoformat(),
        }
    )
    _save_json(_NOTEBOOKS_FILE, notebooks)
    return f"Notebook created: {name} ({nid})"


def list_notebooks() -> str:
    """Return a formatted list of all notebooks."""
    notebooks = _load_json(_NOTEBOOKS_FILE)
    if not notebooks:
        return "No notebooks. Create one with create_notebook."
    lines = ["Notebooks:"]
    for n in notebooks:
        lines.append(f"  {n['name']} ({n['id']})")
    return "\n".join(lines)


def delete_notebook(notebook_id: str) -> str:
    """Delete a notebook by its ID."""
    notebooks = _load_json(_NOTEBOOKS_FILE)
    new_nb = [n for n in notebooks if n["id"] != notebook_id]
    if len(new_nb) == len(notebooks):
        return f"Notebook not found: {notebook_id}"
    _save_json(_NOTEBOOKS_FILE, new_nb)
    return f"Notebook deleted: {notebook_id}"


# ── NOTES ──


def create_note(title: str, content: str = "", notebook_id: str = "") -> str:
    """Create a new note and return a result message."""
    notes = _load_json(_NOTES_FILE)
    note_id = f"note-{len(notes) + 1}"
    now = datetime.now().isoformat()
    notes.append(
        {
            "id": note_id,
            "title": title,
            "content": content,
            "notebook_id": notebook_id,
            "created": now,
            "updated": now,
        }
    )
    _save_json(_NOTES_FILE, notes)
    return f"Note created: {title} ({note_id})"


def list_notes(notebook_id: str = "") -> str:
    """Return a formatted list of notes, optionally filtered by notebook."""
    notes = _load_json(_NOTES_FILE)
    if notebook_id:
        notes = [n for n in notes if n.get("notebook_id") == notebook_id]
    if not notes:
        return "No notes found."
    lines = ["Notes:"]
    for n in notes:
        lines.append(f"  {n['title']} ({n['id']})")
    return "\n".join(lines)


def get_note(note_id: str) -> str:
    """Return the full content of a single note."""
    notes = _load_json(_NOTES_FILE)
    for n in notes:
        if n["id"] == note_id:
            content = n.get("content", "") or "(empty)"
            return f"# {n['title']}\n\n{content}\n\nCreated: {n['created']}"
    return f"Note not found: {note_id}"


def update_note(note_id: str, title: str = "", content: str = "") -> str:
    """Update a note's title and/or content."""
    notes = _load_json(_NOTES_FILE)
    for n in notes:
        if n["id"] == note_id:
            if title:
                n["title"] = title
            if content:
                n["content"] = content
            n["updated"] = datetime.now().isoformat()
            _save_json(_NOTES_FILE, notes)
            return f"Note updated: {n['title']} ({note_id})"
    return f"Note not found: {note_id}"


def delete_note(note_id: str) -> str:
    """Delete a note by its ID."""
    notes = _load_json(_NOTES_FILE)
    new_notes = [n for n in notes if n["id"] != note_id]
    if len(new_notes) == len(notes):
        return f"Note not found: {note_id}"
    _save_json(_NOTES_FILE, new_notes)
    return f"Note deleted: {note_id}"


def search_notes(query: str) -> str:
    """Search notes by title and content, return formatted results."""
    notes = _load_json(_NOTES_FILE)
    q = query.lower()
    results = [
        n for n in notes if q in n["title"].lower() or q in n.get("content", "").lower()
    ]
    if not results:
        return f"No notes matching '{query}'."
    lines = [f"Notes matching '{query}':"]
    for n in results:
        lines.append(f"  {n['title']} ({n['id']})")
    return "\n".join(lines)


def notes_stats() -> str:
    """Return a brief statistics string."""
    notes = _load_json(_NOTES_FILE)
    notebooks = _load_json(_NOTEBOOKS_FILE)
    return f"Notes: {len(notes)} in {len(notebooks)} notebooks"
