"""
Self-improvement loop for Lucas: read backlog → run coding_workspace on next item.

Backlog lives in memory/self_improvements.md (checkbox list under ## Improvements).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from memory.config_manager import get_base_dir

from core.logger import get_logger

logger = get_logger(__name__)

BASE_DIR = get_base_dir()
BACKLOG_PATH = BASE_DIR / "memory" / "self_improvements.md"
LUCAS_WORKSPACE = str(BASE_DIR)

_ITEM_RE = re.compile(
    r"^- \[([ xX])\] \*\*(.+?)\*\*[:\s]*(.*)$",
)


@dataclass
class BacklogItem:
    priority: str
    title: str
    description: str
    done: bool
    line_index: int
    raw_line: str


def _parse_backlog(text: str) -> list[BacklogItem]:
    items: list[BacklogItem] = []
    priority = "general"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("### "):
            priority = line.strip().removeprefix("### ").strip()
        m = _ITEM_RE.match(line.strip())
        if not m:
            continue
        items.append(
            BacklogItem(
                priority=priority,
                title=m.group(2).strip(),
                description=m.group(3).strip(),
                done=m.group(1).lower() == "x",
                line_index=i,
                raw_line=line,
            )
        )
    return items


def _load_items() -> list[BacklogItem]:
    if not BACKLOG_PATH.is_file():
        return []
    return _parse_backlog(BACKLOG_PATH.read_text(encoding="utf-8"))


def _format_list(items: list[BacklogItem], *, pending_only: bool) -> str:
    shown = [it for it in items if not it.done] if pending_only else items
    if not shown:
        return "No backlog items." if pending_only else "Backlog is empty."

    lines = ["Self-improvement backlog:"]
    for n, it in enumerate(shown, 1):
        mark = "done" if it.done else "TODO"
        lines.append(
            f"{n}. [{mark}] ({it.priority}) {it.title}"
            + (f" — {it.description[:100]}" if it.description else "")
        )
    pending = sum(1 for it in items if not it.done)
    lines.append(f"\n{pending} item(s) remaining.")
    return "\n".join(lines)


def _mark_item_done(title: str) -> str:
    if not BACKLOG_PATH.is_file():
        return "Backlog file not found."

    lines = BACKLOG_PATH.read_text(encoding="utf-8").splitlines()
    title_low = title.strip().lower()
    matched = False
    for i, line in enumerate(lines):
        m = _ITEM_RE.match(line.strip())
        if not m or m.group(1).lower() == "x":
            continue
        if m.group(2).strip().lower() == title_low or title_low in m.group(2).lower():
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            matched = True
            break

    if not matched:
        return f"No open item matching title: {title!r}"

    BACKLOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Marked done: {title}"


def _verify_ok(result: str) -> bool:
    return "VERIFY_OK" in (result or "")


def _build_goal(item: BacklogItem) -> str:
    desc = item.description or item.title
    return (
        f"Lucas self-improvement ({item.priority}): {item.title}. "
        f"{desc} "
        "Work only in the Lucas repository. Read AGENTS.md. "
        "Minimal diff; run pytest via coding_workspace verify when done."
    )


def _pick_next(items: list[BacklogItem], title: str = "") -> BacklogItem | None:
    pending = [it for it in items if not it.done]
    if not pending:
        return None
    if title:
        t = title.strip().lower()
        for it in pending:
            if it.title.lower() == t or t in it.title.lower():
                return it
        return None
    return pending[0]


TOOL_SCHEMA = {
    "name": "self_improve",
    "description": (
        "Run Lucas self-improvement from memory/self_improvements.md backlog. "
        "list pending items, run_next to code one item, mark_done when finished."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | run_next | mark_done | status",
            },
            "title": {
                "type": "STRING",
                "description": "run_next/mark_done: specific backlog item title",
            },
        },
        "required": ["action"],
    },
}


def self_improve(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    p = parameters or {}
    action = (p.get("action") or "list").lower().strip()
    title = (p.get("title") or "").strip()

    items = _load_items()

    if action in ("list", "status"):
        pending = [it for it in items if not it.done]
        if action == "status":
            return (
                f"backlog: {BACKLOG_PATH}\n"
                f"workspace: {LUCAS_WORKSPACE}\n"
                f"total: {len(items)}, pending: {len(pending)}, done: {len(items) - len(pending)}"
            )
        return _format_list(items, pending_only=True)

    if action == "mark_done":
        if not title:
            return "title is required for mark_done."
        return _mark_item_done(title)

    if action == "run_next":
        item = _pick_next(items, title)
        if not item:
            if title:
                return f"No pending item matching {title!r}. Use action=list."
            return "All self-improvement items are done, sir."

        goal = _build_goal(item)
        if speak:
            speak(f"Working on self-improvement: {item.title}.")

        from actions.coding_workspace import coding_workspace

        result = coding_workspace(
            {
                "action": "task",
                "goal": goal,
                "workspace_path": LUCAS_WORKSPACE,
            },
            response=response,
            player=player,
            session_memory=session_memory,
            speak=speak,
        )

        header = (
            f"Self-improvement: ({item.priority}) {item.title}\n"
        )
        if _verify_ok(result or ""):
            mark_msg = _mark_item_done(item.title)
            header += f"{mark_msg} (tests/lint passed).\n\n"
        else:
            header += (
                f"Still open — verify failed or incomplete. "
                f"Fix manually or retry, then "
                f"self_improve mark_done title={item.title!r}\n\n"
            )
        return header + (result or "")[:12000]

    return "Unknown action. Use list, status, run_next, or mark_done."
