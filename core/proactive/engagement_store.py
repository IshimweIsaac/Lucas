"""Engagement history store — memory/proactive_engagement.json.

Appends every proactive engagement (spoken or queued), keeps the newest
ENGAGEMENT_MAX entries, and holds the date-keyed daily budget counters
(SPEC sections 5 and 7).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

ENGAGEMENT_FILE: Path = get_base_dir() / "memory" / "proactive_engagement.json"
ENGAGEMENT_MAX: int = 500

_lock = threading.Lock()

_COUNTER_KEYS = ("llm", "web", "reads", "speech")


def _empty_store() -> dict:
    return {"version": 1, "entries": [], "daily_counters": {}}


def _empty_counters(today: str | None = None) -> dict:
    return {
        "date": today or datetime.now().strftime("%Y-%m-%d"),
        "llm": 0,
        "web": 0,
        "reads": 0,
        "speech": 0,
    }


def load_store() -> dict:
    """Load the engagement store, filling missing structure with defaults."""
    if not ENGAGEMENT_FILE.exists():
        return _empty_store()
    with _lock:
        try:
            data = json.loads(ENGAGEMENT_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("proactive: failed to load engagement store (%s)", exc)
            return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    base = _empty_store()
    for key in base:
        if key not in data:
            data[key] = base[key]
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    if not isinstance(data.get("daily_counters"), dict):
        data["daily_counters"] = {}
    return data


def save_store(data: dict) -> None:
    ENGAGEMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        ENGAGEMENT_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def get_daily_counters() -> dict:
    """Return today's counters, rolling over the date key when the day changes."""
    data = load_store()
    counters = data["daily_counters"]
    today = datetime.now().strftime("%Y-%m-%d")
    if counters.get("date") != today:
        counters = _empty_counters(today)
        data["daily_counters"] = counters
        save_store(data)
    return counters


def bump_counter(kind: str, n: int = 1) -> dict:
    """Increment one daily counter and persist. Unknown kinds are ignored."""
    if kind not in _COUNTER_KEYS:
        return get_daily_counters()
    data = load_store()
    counters = data["daily_counters"]
    today = datetime.now().strftime("%Y-%m-%d")
    if counters.get("date") != today:
        counters = _empty_counters(today)
        data["daily_counters"] = counters
    counters[kind] = int(counters.get(kind, 0)) + max(1, int(n))
    save_store(data)
    return counters


def append_entry(entry: dict) -> dict:
    """Append an engagement entry, assign an id, cap at ENGAGEMENT_MAX."""
    data = load_store()
    entries = data["entries"]
    seq = len(entries) + 1
    new_entry = dict(entry)
    new_entry["id"] = new_entry.get("id") or f"pe-{seq}"
    new_entry.setdefault("at", datetime.now().isoformat(timespec="seconds"))
    new_entry.setdefault("kind", "insight")
    new_entry.setdefault("score", 0.0)
    new_entry.setdefault("source", "")
    new_entry.setdefault("status", "queued")
    new_entry.setdefault("outcome_ref", None)
    new_entry.setdefault("body", "")
    entries.append(new_entry)
    if len(entries) > ENGAGEMENT_MAX:
        data["entries"] = entries[-ENGAGEMENT_MAX:]
    save_store(data)
    return new_entry


def recent_entries(limit: int = 10) -> list[dict]:
    data = load_store()
    return list(reversed(data["entries"]))[: max(0, int(limit))]


def recent_topics(limit: int = 10) -> list[str]:
    return [e.get("title") or "" for e in recent_entries(limit)]


def last_engagement() -> dict | None:
    data = load_store()
    entries = data.get("entries") or []
    return entries[-1] if entries else None


def mark_status(entry_id: str, status: str) -> bool:
    """Set an entry's status (spoken/queued/dismissed/acknowledged)."""
    valid = {"spoken", "queued", "dismissed", "acknowledged"}
    if status not in valid:
        return False
    data = load_store()
    for entry in data["entries"]:
        if entry.get("id") == entry_id:
            entry["status"] = status
            save_store(data)
            return True
    return False


def digest(limit: int = 3) -> str:
    """Compact digest of recent engagements for the curator prompt (follow-up)."""
    entries = recent_entries(limit)
    if not entries:
        return "No recent proactive engagements."
    lines = []
    for entry in entries:
        title = (entry.get("title") or "untitled")[:120]
        lines.append(f"- {title} [{entry.get('status', '?')}]")
    return "\n".join(lines)