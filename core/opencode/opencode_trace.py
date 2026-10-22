"""Compact OpenCode trace digest — full visibility for Lucas, not for speech."""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

_MAX_DIGEST_CHARS = 3000
_MAX_TRACE_AGE = 1800
_MAX_TOOLS = 20
_MAX_THINKING = 10
_MAX_SUBAGENTS = 12
_MAX_TODOS = 8

_THINKING_RE = re.compile(
    r"the user (is|just|has)|i should|i'll |i will |let me |casual greeting|respond concis",
    re.I,
)

_trace_lock = threading.Lock()
_trace_handler: Callable[[str], None] | None = None


def set_trace_handler(fn: Callable[[str], None] | None) -> None:
    global _trace_handler
    _trace_handler = fn


class OpenCodeTrace:
    """Rolling digest of an OpenCode job — mirrors UI tracker, compact for Live context."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.token = ""
        self.session_id = ""
        self.goal = ""
        self.workspace = ""
        self.phase = ""
        self.started_at = 0.0
        self.tools: list[str] = []
        self.thinking: list[str] = []
        self.subagents: list[str] = []
        self.todos: list[str] = []
        self.diffs: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.last_reply = ""
        self._seen_tools: set[str] = set()
        self._seen_thinking: set[str] = set()
        self._seen_todos: set[str] = set()
        self._seen_diffs: set[str] = set()
        self._part_text: dict[str, str] = {}
        self._last_digest = ""

    def ingest_job(self, payload: dict[str, Any]) -> None:
        data = dict(payload or {})
        token = str(data.get("token") or "")
        if token and token != self.token:
            self.reset()
            self.token = token
        sid = str(data.get("session_id") or "")
        if sid:
            self.session_id = sid
        goal = str(data.get("goal") or data.get("label") or "").strip()
        if goal:
            self.goal = goal[:200]
        ws = str(data.get("workspace") or "").strip()
        if ws:
            self.workspace = ws
        phase = str(data.get("phase") or "")
        if phase:
            self.phase = phase
        if data.get("started_at"):
            self.started_at = float(data.get("started_at") or 0)

    def ingest_event(self, event_type: str, props: dict[str, Any]) -> None:
        et = (event_type or "").strip()
        if et in ("message.part.updated", "message.part.delta"):
            part = props.get("part") or {}
            if isinstance(part, dict):
                self._ingest_part(part, delta=props.get("delta"))
            return

        if et in ("session.status", "session.idle"):
            st = props.get("status") or ("idle" if et == "session.idle" else "")
            if st:
                self.phase = str(st)
            return

        if et == "session.error":
            msg = str(props.get("message") or props.get("error") or "session error")
            if msg not in self.errors:
                self.errors.append(msg[:120])

        if et == "permission.asked":
            perm = str(props.get("permission") or props.get("title") or "?")
            line = f"permission: {perm}"
            if line not in self.warnings:
                self.warnings.append(line)

        if et == "session.diff":
            files = props.get("files") or props.get("diff") or []
            if isinstance(files, list):
                for f in files[:6]:
                    if isinstance(f, dict):
                        path = str(f.get("path") or f.get("file") or "")
                    else:
                        path = str(f)
                    if path and path not in self._seen_diffs:
                        self._seen_diffs.add(path)
                        self.diffs.append(path)

        if et == "todo.updated":
            todos = props.get("todos") or []
            for t in todos if isinstance(todos, list) else []:
                if not isinstance(t, dict):
                    continue
                content = str(t.get("content") or t.get("title") or "").strip()
                if not content or content in self._seen_todos:
                    continue
                self._seen_todos.add(content)
                mark = "done" if t.get("done") or t.get("status") == "done" else "open"
                self.todos.append(f"[{mark}] {content[:80]}")

    def ingest(self, payload: dict[str, Any]) -> None:
        self.ingest_job(payload)
        event_type = payload.get("event_type")
        props = payload.get("properties")
        if event_type and isinstance(props, dict):
            self.ingest_event(str(event_type), props)
        err = str(payload.get("error") or "").strip()
        if err and err not in self.errors:
            self.errors.append(err[:120])

    def _ingest_part(self, part: dict[str, Any], *, delta: Any = None) -> None:
        pid = str(part.get("id") or "")
        ptype = str(part.get("type") or "")
        raw = str(
            delta if delta is not None else (part.get("text") or part.get("content") or "")
        )
        if not raw:
            return

        if ptype in ("reasoning", "thinking"):
            self._add_thinking(raw)
            return

        if ptype in ("tool-invocation", "tool", "tool-call", "tool_use"):
            tool = str(part.get("tool") or part.get("name") or "tool")
            inp = part.get("input") or part.get("arguments")
            line = tool if not inp else f"{tool} {str(inp)[:60]}"
            key = line[:80]
            if key not in self._seen_tools:
                self._seen_tools.add(key)
                self.tools.append(line[:100])
            return

        if ptype in ("tool-result", "tool_result"):
            out = str(part.get("output") or part.get("result") or raw)[:80]
            line = f"→ {out}"
            if line not in self._seen_tools:
                self._seen_tools.add(line)
                self.tools.append(line)
            return

        if str(part.get("role") or "").lower() == "user":
            return

        if ptype not in ("text", "") and ptype != "text":
            return

        if raw and _THINKING_RE.search(raw) and len(raw) < 200:
            self._add_thinking(raw)
            return

        prev = self._part_text.get(pid, "")
        if delta is not None:
            new_text = prev + raw
        elif raw.startswith(prev):
            new_text = raw
        else:
            new_text = prev + raw if raw not in prev else prev

        if new_text.strip():
            self._part_text[pid] = new_text
            if new_text.strip() != self.goal:
                self.last_reply = new_text.strip()[:400]

    def _add_thinking(self, raw: str) -> None:
        line = raw.strip().split("\n")[0][:100]
        if not line or line in self._seen_thinking:
            return
        self._seen_thinking.add(line)
        self.thinking.append(line)

    def note_subagents(self, children: list[dict[str, Any]]) -> None:
        for child in children:
            if not isinstance(child, dict):
                continue
            sid = str(child.get("id") or child.get("sessionID") or "")
            title = str(child.get("title") or child.get("name") or sid[:12] or "?")[:50]
            line = f"{title} ({sid[:10]}…)" if sid else title
            if line not in self.subagents:
                self.subagents.append(line)

    def format_digest(self) -> str:
        lines: list[str] = []
        if self.goal:
            lines.append(f"goal: {self.goal}")
        if self.session_id:
            lines.append(f"session: {self.session_id}")
        if self.workspace:
            lines.append(f"workspace: {self.workspace}")
        if self.phase:
            age = ""
            if self.started_at:
                age = f" ({int(time.time() - self.started_at)}s)"
            lines.append(f"phase: {self.phase}{age}")

        if self.thinking:
            lines.append("thinking:")
            for t in self.thinking[-_MAX_THINKING:]:
                lines.append(f"  · {t}")

        if self.tools:
            lines.append("tools:")
            for t in self.tools[-_MAX_TOOLS:]:
                lines.append(f"  · {t}")

        if self.subagents:
            lines.append(f"sub-agents ({len(self.subagents)}):")
            for s in self.subagents[-_MAX_SUBAGENTS:]:
                lines.append(f"  · {s}")

        if self.todos:
            lines.append("todos:")
            for t in self.todos[-_MAX_TODOS:]:
                lines.append(f"  · {t}")

        if self.diffs:
            lines.append("files changed:")
            for d in self.diffs[-6:]:
                lines.append(f"  · {d}")

        if self.warnings:
            lines.append("blocked:")
            for w in self.warnings[-3:]:
                lines.append(f"  · {w}")

        if self.errors:
            lines.append("errors:")
            for e in self.errors[-3:]:
                lines.append(f"  · {e}")

        if self.last_reply:
            preview = self.last_reply[:200]
            if len(self.last_reply) > 200:
                preview += "…"
            lines.append(f"latest reply: {preview}")

        text = "\n".join(lines).strip()
        if len(text) > _MAX_DIGEST_CHARS:
            text = text[: _MAX_DIGEST_CHARS - 1] + "…"
        self._last_digest = text
        return text

    def digest_changed(self) -> bool:
        current = self.format_digest()
        return bool(current) and current != self._last_digest


_traces: dict[str, OpenCodeTrace] = {}


def _trace_for(token: str) -> OpenCodeTrace:
    token = (token or "").strip() or "_default"
    now = time.time()
    for tkey in list(_traces):
        started = _traces[tkey].started_at
        if started and now - started > _MAX_TRACE_AGE:
            del _traces[tkey]
    if token not in _traces:
        t = OpenCodeTrace()
        t.started_at = now
        _traces[token] = t
    return _traces[token]


def reset(token: str = "") -> None:
    with _trace_lock:
        if token:
            _traces.pop(token, None)
        else:
            _traces.clear()


def remove(token: str) -> None:
    reset(token)


def ingest(payload: dict[str, Any]) -> str:
    token = str(payload.get("token") or "").strip() or "_default"
    with _trace_lock:
        trace = _trace_for(token)
        trace.ingest(payload)
        digest = _format_all_locked()
    if digest and _trace_handler:
        try:
            _trace_handler(digest)
        except Exception:
            pass
    return digest


def _format_all_locked() -> str:
    if not _traces:
        return ""
    blocks: list[str] = []
    for token, trace in sorted(_traces.items(), key=lambda kv: kv[1].started_at or 0):
        body = trace.format_digest()
        if not body:
            continue
        short = token[-8:] if len(token) > 8 else token
        blocks.append(f"--- job {short} ---\n{body}")
    text = "\n\n".join(blocks).strip()
    if len(text) > _MAX_DIGEST_CHARS * 2:
        text = text[: _MAX_DIGEST_CHARS * 2 - 1] + "…"
    return text


def format_digest(token: str = "") -> str:
    with _trace_lock:
        if token:
            return _trace_for(token).format_digest()
        return _format_all_locked()


def note_subagents(token: str, children: list[dict[str, Any]]) -> None:
    token = (token or "").strip() or "_default"
    with _trace_lock:
        _trace_for(token).note_subagents(children)
        digest = _format_all_locked()
    if digest and _trace_handler:
        try:
            _trace_handler(digest)
        except Exception:
            pass
