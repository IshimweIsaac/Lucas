"""Research ideas store — memory/research_ideas.json.

Rotates interest-derived research topics: `pick_next_topic` returns the
least-used idea not researched within the recent window, `mark_done` records
results and pushes the idea into `recent` so it is not repeated too soon.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

IDEAS_FILE: Path = get_base_dir() / "memory" / "research_ideas.json"
NOT_REPEAT_DAYS_DEFAULT = 7
RECENT_MAX = 30

_lock = threading.Lock()

_PREFERENCE_HINT_TERMS = ("interest", "tech", "wish")


def _empty() -> dict:
    return {"version": 1, "ideas": [], "recent": []}


def load() -> dict:
    if not IDEAS_FILE.exists():
        return _empty()
    with _lock:
        try:
            data = json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("proactive: failed to load research ideas (%s)", exc)
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("ideas", [])
    data.setdefault("recent", [])
    if not isinstance(data["ideas"], list):
        data["ideas"] = []
    if not isinstance(data["recent"], list):
        data["recent"] = []
    return data


def save(data: dict) -> None:
    IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        IDEAS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def topics() -> list[dict]:
    return list(load().get("ideas", []))


def add_idea(topic: str, interest_source: str) -> str:
    """Add a topic idea. Returns the new id, or '' when the topic is a duplicate."""
    topic = (topic or "").strip()
    if not topic:
        return ""
    data = load()
    for idea in data["ideas"]:
        if idea.get("topic", "").strip().lower() == topic.lower():
            return ""
    seq = len(data["ideas"]) + 1
    idea_id = f"ri-{seq:04d}"
    data["ideas"].append(
        {
            "id": idea_id,
            "interest_source": interest_source,
            "topic": topic[:380],
            "status": "idea",
            "last_researched": None,
            "times_researched": 0,
            "last_result": "",
            "created": datetime.now().strftime("%Y-%m-%d"),
        }
    )
    save(data)
    return idea_id


def seed_from_memory(memory: dict) -> int:
    """Seed week-one topics from the interests category and interest-like
    preference keys. Skips topics that already exist. Returns count added."""
    added = 0
    interests = memory.get("interests", {}) if isinstance(memory, dict) else {}
    if isinstance(interests, dict):
        for key, entry in interests.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            value = str(value or "").strip()
            if value and add_idea(value, f"memory:interests:{key}"):
                added += 1

    preferences = memory.get("preferences", {}) if isinstance(memory, dict) else {}
    if isinstance(preferences, dict):
        for key, entry in preferences.items():
            low_key = key.lower()
            if not any(term in low_key for term in _PREFERENCE_HINT_TERMS):
                continue
            value = entry.get("value") if isinstance(entry, dict) else entry
            value = str(value or "").strip()
            if value and add_idea(value, f"memory:preferences:{key}"):
                added += 1
    return added


def pick_next_topic(*, not_repeat_days: int = NOT_REPEAT_DAYS_DEFAULT) -> dict | None:
    """Least-used idea with status 'idea' that is not in the recent window."""
    data = load()
    recent = [r for r in (data.get("recent") or []) if r][-not_repeat_days:]
    candidates = [
        idea
        for idea in data["ideas"]
        if idea.get("status") == "idea" and idea.get("id") not in recent
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda i: (
            int(i.get("times_researched", 0)),
            i.get("last_researched") is not None,
            i.get("last_researched") or "",
            i.get("created") or "",
        )
    )
    return dict(candidates[0])


def mark_done(topic_id: str, result: str = "", status: str = "researched") -> None:
    """Record a research result and push the topic into the recent window."""
    data = load()
    today = datetime.now().strftime("%Y-%m-%d")
    for idea in data["ideas"]:
        if idea.get("id") != topic_id:
            continue
        idea["status"] = status
        idea["last_researched"] = today
        idea["times_researched"] = int(idea.get("times_researched", 0)) + 1
        idea["last_result"] = (result or "")[:2000]
        break
    recent = [r for r in data.get("recent", []) if r != topic_id]
    recent.append(topic_id)
    data["recent"] = recent[-RECENT_MAX:]
    save(data)


def to_prompt() -> str:
    """Human-readable topic list for the proactive tool."""
    data = load()
    if not data["ideas"]:
        return "No research ideas stored yet."
    lines = []
    for idea in data["ideas"]:
        lines.append(
            f"- {idea['id']}: {idea['topic']} [{idea.get('status', 'idea')}, "
            f"researched {idea.get('times_researched', 0)}x]"
        )
    return "\n".join(lines)