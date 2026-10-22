"""Last OpenCode reply — for status only."""

from __future__ import annotations

import time
from typing import Callable


def last_turn(state: dict) -> dict:
    raw = state.get("last_opencode") or {}
    return raw if isinstance(raw, dict) else {}


def record_turn(
    load_state: Callable[[], dict],
    save_state: Callable[[dict], None],
    *,
    action: str,
    goal: str,
    reply: str,
    session_id: str,
) -> None:
    state = load_state()
    state["last_opencode"] = {
        "action": action,
        "goal": (goal or "")[:500],
        "reply": (reply or "")[:800],
        "session_id": session_id,
        "at": time.time(),
    }
    save_state(state)
