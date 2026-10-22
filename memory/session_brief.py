"""
Rolling session brief — survives Gemini Live reconnects without full chat history.

Stores short factual bullets only (capped) to reduce hallucination from huge context.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from threading import Lock

from memory.config_manager import get_base_dir

BASE_DIR = get_base_dir()
BRIEF_PATH = BASE_DIR / "memory" / "session_brief.json"

_lock = Lock()
MAX_BULLETS = 14
MAX_BULLET_CHARS = 160
MAX_TOTAL_CHARS = 900
MAX_TURN_CHARS = 120

_LUMINA_RE = re.compile(r"\blumina\b", re.IGNORECASE)

_STALE_TIME_BULLET_RE = re.compile(
    r"^Lucas:.*\b("
    r"time is|current time|the time is|current date is|date is tuesday|date is monday"
    r")\b",
    re.IGNORECASE,
)

_ASSISTANT_TIME_GUESS_RE = re.compile(
    r"\b(current\s+)?time\s+is\s+\d{1,2}:\d{2}",
    re.IGNORECASE,
)

_CLEAR_PHRASES = (
    "new topic",
    "fresh start",
    "start over",
    "forget this conversation",
    "clear context",
    "reset conversation",
)


def _empty() -> dict:
    return {
        "updated": "",
        "topic": "",
        "bullets": [],
        "coding_workspace": "",
        "opencode_trace": "",
    }


def load_brief() -> dict:
    if not BRIEF_PATH.exists():
        return _empty()
    with _lock:
        try:
            data = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return _empty()
            data.setdefault("bullets", [])
            data.setdefault("topic", "")
            data.setdefault("updated", "")
            data.setdefault("coding_workspace", "")
            data.setdefault("opencode_trace", "")
            return data
        except Exception as e:
            print(f"[SessionBrief] ⚠️ Load error: {e}")
            return _empty()


def _save(data: dict) -> None:
    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    BRIEF_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        BRIEF_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _trim(data: dict) -> dict:
    bullets: list[str] = []
    for b in data.get("bullets", []):
        if not isinstance(b, str):
            continue
        b = b.strip()
        if not b:
            continue
        if len(b) > MAX_BULLET_CHARS:
            b = b[: MAX_BULLET_CHARS - 1].rstrip() + "…"
        bullets.append(b)

    while len(bullets) > MAX_BULLETS:
        bullets.pop(0)

    while bullets and len(json.dumps({"bullets": bullets}, ensure_ascii=False)) > MAX_TOTAL_CHARS:
        bullets.pop(0)

    data["bullets"] = bullets
    topic = (data.get("topic") or "").strip()
    if len(topic) > 80:
        topic = topic[:77] + "…"
    data["topic"] = topic
    return data


def clear_brief() -> None:
    _save(_empty())
    print("[SessionBrief] 🗑️ Cleared")


def set_topic(topic: str) -> None:
    topic = (topic or "").strip()
    if not topic:
        return
    data = load_brief()
    data["topic"] = topic[:80]
    _save(_trim(data))


def _user_mentioned_lumina_recently() -> bool:
    data = load_brief()
    for bullet in data.get("bullets", [])[-10:]:
        if bullet.lower().startswith("user:") and _LUMINA_RE.search(bullet):
            return True
    return False


def add_bullet(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    if _LUMINA_RE.search(text) and not _user_mentioned_lumina_recently():
        return
    data = load_brief()
    bullets = data.get("bullets", [])
    if bullets and bullets[-1] == text:
        return
    bullets.append(text)
    data["bullets"] = bullets
    _save(_trim(data))


def _one_line(text: str, limit: int = MAX_TURN_CHARS) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _user_wants_clear(user_text: str) -> bool:
    low = (user_text or "").lower()
    return any(p in low for p in _CLEAR_PHRASES)


def note_turn(user_text: str = "", assistant_text: str = "") -> None:
    """Record a completed voice turn (short bullets)."""
    user_text = _one_line(user_text)
    assistant_text = _one_line(assistant_text)

    if user_text and _user_wants_clear(user_text):
        clear_brief()
        add_bullet("User started a new topic.")
        return

    if user_text:
        add_bullet(f"User: {user_text}")
    if assistant_text:
        if _ASSISTANT_TIME_GUESS_RE.search(assistant_text):
            assistant_text = ""
        if _LUMINA_RE.search(assistant_text) and not _LUMINA_RE.search(user_text):
            if not _user_mentioned_lumina_recently():
                assistant_text = _LUMINA_RE.sub("the project", assistant_text)
        add_bullet(f"Lucas: {assistant_text}")


def note_tool(tool_name: str, result: str, args: dict | None = None) -> None:
    """Record a tool call outcome (facts only, truncated)."""
    if tool_name == "save_memory":
        return

    summary = _one_line(str(result), 100)
    if not summary:
        summary = "done"

    extra = ""
    if args:
        if tool_name == "coding_workspace":
            action = args.get("action", "")
            ws = args.get("workspace_path", "")
            goal = args.get("goal", "")
            if action:
                extra = f" action={action}"
            if ws:
                extra += f" ws={Path(str(ws)).name}"
            if goal and action == "task":
                extra += f" goal={_one_line(goal, 60)}"
        elif tool_name == "agent_task" and args.get("goal"):
            extra = f" goal={_one_line(str(args['goal']), 60)}"

    # OpenCode control — extract key info
    if tool_name == "opencode_control":
        action = (args or {}).get("action", "")
        goal = (args or {}).get("goal", "")
        if action and goal:
            bullet = f"Lucas: OpenCode {action} — {goal[:100]}"
            trimmed = bullet[:MAX_BULLET_CHARS]
            add_bullet(trimmed)
            return
        elif action:
            bullet = f"Lucas: OpenCode {action}"
            add_bullet(bullet[:MAX_BULLET_CHARS])
            return

    # OPENCODE SAYS — capture result
    if "OPENCODE SAYS" in (result or "") and not tool_name.startswith("opencode_"):
        for line in (result or "").split("\n"):
            line = line.strip()
            if line and not line.startswith("OPENCODE"):
                bullet = f"OpenCode: {line[:100]}"
                add_bullet(bullet[:MAX_BULLET_CHARS])
                return

    add_bullet(f"Tool {tool_name}{extra}: {summary}")


def ensure_default_workspace(default_path: str) -> None:
    """Pin default repo when none set (voice routing after reconnect)."""
    data = load_brief()
    if (data.get("coding_workspace") or "").strip():
        return
    pin_coding_workspace(default_path)


def pin_coding_workspace(path: str) -> None:
    """Remember active repo path for voice routing after reconnect."""
    path = (path or "").strip()
    if not path:
        return
    try:
        resolved = str(Path(path).expanduser().resolve())
    except Exception:
        resolved = path
    data = load_brief()
    if data.get("coding_workspace") == resolved:
        return
    data["coding_workspace"] = resolved
    _save(_trim(data))


def pin_opencode_trace(trace: str) -> None:
    """Pin a compact OpenCode trace digest to the brief.

    The trace is truncated to MAX_BULLET_CHARS to stay within brief limits.
    """
    if not trace or not trace.strip():
        return
    with _lock:
        brief = load_brief()
        brief["opencode_trace"] = trace.strip()[:MAX_BULLET_CHARS]
        _save(brief)


def clear_opencode_trace() -> None:
    """Clear the OpenCode trace from the brief."""
    with _lock:
        brief = load_brief()
        brief["opencode_trace"] = ""
        _save(brief)


def note_reconnect() -> None:
    data = load_brief()
    if not data.get("bullets") and not data.get("topic"):
        return
    add_bullet("Live session reconnected — continue from brief below.")


def format_for_prompt() -> str:
    data = load_brief()
    bullets = data.get("bullets", [])
    topic = (data.get("topic") or "").strip()
    ws = (data.get("coding_workspace") or "").strip()
    if not bullets and not topic and not ws:
        return ""

    lines = [
        "[SESSION BRIEF — factual recap only; do not invent details not listed here]",
    ]
    if topic:
        lines.append(f"Current topic: {topic}")
    ws = (data.get("coding_workspace") or "").strip()
    if ws:
        lines.append(f"Active coding workspace: {ws}")
    try:
        from core.path_utils import known_paths

        kp = known_paths()[:10]
        if kp:
            lines.append("Known real paths (never invent others):")
            for p in kp:
                lines.append(f"  • {p}")
    except Exception:
        pass
    updated = data.get("updated", "")
    if updated:
        lines.append(f"Last updated: {updated}")
    lines.append("Recent facts:")
    for b in bullets[-MAX_BULLETS:]:
        if _STALE_TIME_BULLET_RE.match(b.strip()):
            continue
        lines.append(f"  • {b}")
    lines.append(
        "If the user continues an earlier task, use this brief. "
        "NEVER invent file paths — only use paths listed here or from path_helper/file_controller. "
        "Linux paths are case-sensitive (Documents not documents)."
    )

    # Append OpenCode trace if present
    if data.get("opencode_trace"):
        trace = data["opencode_trace"][:MAX_BULLET_CHARS]
        lines.append(f"[OPENCODE LIVE — internal trace, do NOT read aloud]\n{trace}\n")

    text = "\n".join(lines)
    if len(text) > MAX_TOTAL_CHARS + 200:
        text = text[: MAX_TOTAL_CHARS + 197] + "…"
    return text + "\n"
