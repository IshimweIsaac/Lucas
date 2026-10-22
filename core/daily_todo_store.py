"""Daily todo storage — JSON-backed CRUD with atomic writes and change listeners."""

from __future__ import annotations

import json
import logging
import threading
import uuid as _uuid
from datetime import datetime
from typing import Any, Callable

from memory.config_manager import get_base_dir

logger = logging.getLogger("lucas.daily_todo_store")


# ── paths & constants ────────────────────────────────────────────────────────

BASE_DIR = get_base_dir()
STORE_PATH = BASE_DIR / "memory" / "daily_todo_store.json"

PRIORITIES = frozenset({"p0", "p1", "p2", "p3"})

EMPTY: dict[str, Any] = {"todos": {}, "order": [], "archived": []}

_lock = threading.Lock()
_change_callbacks: list[Callable[[], None]] = []


# ── internal helpers ─────────────────────────────────────────────────────────

def _load() -> dict[str, Any]:
    """Load store from disk, returning EMPTY if missing or corrupt."""
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "todos" in data and "order" in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return dict(EMPTY)


def _save(data: dict[str, Any]) -> None:
    """Atomically write *data* to STORE_PATH."""
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STORE_PATH)


def _notify() -> None:
    """Call all registered change listeners."""
    for cb in _change_callbacks:
        try:
            cb()
        except Exception:
            logger.exception("daily_todo_store change callback failed")


def _next_id() -> str:
    return _uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── public API ───────────────────────────────────────────────────────────────

def list_todos(*, section: str = "", done: bool | None = None) -> list[dict]:
    """Return todos, optionally filtered by *section* and/or *done* status."""
    with _lock:
        data = _load()
        todos: list[dict] = []
        for tid in data.get("order", []):
            t = data.get("todos", {}).get(tid)
            if t is None:
                continue
            t = dict(t)
            t["id"] = tid
            if section and t.get("section", "") != section:
                continue
            if done is not None and t.get("done", False) != done:
                continue
            todos.append(t)
        return todos


def add_todo(
    title: str,
    *,
    priority: str = "p2",
    section: str = "morning",
    due_date: str = "",
    notes: str = "",
) -> dict | None:
    """Add a new todo and return its record, or None on failure."""
    if not title or not title.strip():
        return None
    priority = priority if priority in PRIORITIES else "p2"
    with _lock:
        data = _load()
        tid = _next_id()
        record = {
            "title": title.strip(),
            "priority": priority,
            "section": section,
            "due_date": due_date,
            "notes": notes,
            "done": False,
            "created": _now_iso(),
        }
        data.setdefault("todos", {})[tid] = record
        data.setdefault("order", []).append(tid)
        _save(data)
    _notify()
    return {**record, "id": tid}


def get_todo(todo_id: str) -> dict | None:
    """Return a single todo dict, or None if not found."""
    with _lock:
        data = _load()
        record = data.get("todos", {}).get(todo_id)
        if record is None:
            return None
        return {**record, "id": todo_id}


def update_todo(todo_id: str, **updates: Any) -> dict | None:
    """Update fields on an existing todo and return the updated record."""
    with _lock:
        data = _load()
        record = data.get("todos", {}).get(todo_id)
        if record is None:
            return None
        for key in ("title", "priority", "section", "due_date", "notes", "done"):
            if key in updates:
                record[key] = updates[key]
        _save(data)
    _notify()
    return {**record, "id": todo_id}


def toggle_todo(todo_id: str) -> dict | None:
    """Toggle the *done* flag on a todo."""
    with _lock:
        data = _load()
        record = data.get("todos", {}).get(todo_id)
        if record is None:
            return None
        record["done"] = not record.get("done", False)
        _save(data)
    _notify()
    return {**record, "id": todo_id}


def delete_todo(todo_id: str) -> bool:
    """Remove a todo completely. Returns True if it existed."""
    with _lock:
        data = _load()
        if todo_id not in data.get("todos", {}):
            return False
        del data["todos"][todo_id]
        try:
            data.setdefault("order", []).remove(todo_id)
        except ValueError:
            logger.warning("daily_todo_store: todo %s not in order list", todo_id)
        _save(data)
    _notify()
    return True


def archive_done() -> int:
    """Move all done todos to the archived list. Returns count archived."""
    with _lock:
        data = _load()
        todos = data.get("todos", {})
        order = data.get("order", [])
        done_ids = [tid for tid in order if todos.get(tid, {}).get("done")]
        for tid in done_ids:
            order.remove(tid)
            archived = data.setdefault("archived", [])
            archived.append({"id": tid, **todos.pop(tid)})
        archived = data.get("archived", [])
        if len(archived) > 100:
            data["archived"] = archived[-100:]
        _save(data)
    if done_ids:
        _notify()
    return len(done_ids)


def reorder(order: list[str]) -> bool:
    """Replace the order list. Returns True on success."""
    with _lock:
        data = _load()
        existing = set(data.get("todos", {}))
        if not all(tid in existing for tid in order):
            return False
        data["order"] = list(order)
        _save(data)
    _notify()
    return True


def stats() -> dict:
    """Return summary stats about the store."""
    with _lock:
        data = _load()
        todos = data.get("todos", {})
        total = len(todos)
        done_count = sum(1 for t in todos.values() if t.get("done"))
    return {
        "total": total,
        "done": done_count,
        "pending": total - done_count,
        "archived": len(data.get("archived", [])),
    }


def on_change(cb: Callable[[], None]) -> None:
    """Register a callback invoked after every mutation."""
    _change_callbacks.append(cb)


def reset_store() -> None:
    """Clear all data (used in tests)."""
    with _lock:
        _save(dict(EMPTY))
    _notify()
