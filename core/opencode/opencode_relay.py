"""Stream OpenCode assistant text to Lucas as it arrives (not only at job end)."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from typing import Any

from core.opencode import opencode_jobs as oc_jobs

_THINKING_RE = re.compile(
    r"the user (is|just|has)|i should|i'll |i will |let me |casual greeting|respond concis",
    re.I,
)

Meta = dict[str, Any]
ReplyHandler = Callable[[str, bool, Meta], None]


class ReplyRelay:
    """Accumulate assistant reply text from SSE; push to Lucas incrementally."""

    def __init__(self, token: str, on_reply: ReplyHandler | None, *, meta: Meta | None = None):
        self._token = token
        self._on_reply = on_reply
        self._meta = dict(meta or {})
        self._meta.setdefault("token", token)
        self._buf = ""
        self._last_sent = ""
        self._final_sent = False
        self._lock = threading.Lock()
        self._debounce: threading.Timer | None = None

    def final_text(self) -> str:
        with self._lock:
            return self._buf.strip()

    def reset(self) -> None:
        """Clear accumulated state for reuse across multi-turn conversations.

        Cancels any pending debounce timer and resets buffer, last-sent
        tracking, and final-sent flag so the next turn starts fresh.
        """
        with self._lock:
            if self._debounce:
                self._debounce.cancel()
                self._debounce = None
            self._buf = ""
            self._last_sent = ""
            self._final_sent = False

    def close(self) -> None:
        with self._lock:
            if self._debounce:
                self._debounce.cancel()
                self._debounce = None
            should_emit = not self._final_sent and bool(self._buf.strip())
        if should_emit:
            self._emit(final=True)

    def on_event(self, event_type: str, props: dict[str, Any]) -> None:
        if event_type not in ("message.part.updated", "message.part.delta"):
            if event_type == "session.idle":
                self.close()
            return

        part = props.get("part") or {}
        if not isinstance(part, dict):
            return

        ptype = str(part.get("type") or "")
        if ptype in ("reasoning", "thinking"):
            return
        if ptype and ptype not in ("text", ""):
            return
        if str(part.get("role") or "").lower() == "user":
            return

        delta = props.get("delta")
        chunk = str(delta) if delta is not None else str(part.get("text") or part.get("content") or "")
        if not chunk:
            return
        if _THINKING_RE.search(chunk) and len(chunk) < 200:
            return

        with self._lock:
            if not oc_jobs.is_token_active(self._token):
                return
            if delta is not None:
                self._buf += chunk
            elif chunk.startswith(self._buf):
                self._buf = chunk
            elif chunk not in self._buf:
                self._buf += chunk

        self._schedule_emit()

    def _schedule_emit(self) -> None:
        with self._lock:
            if self._debounce:
                self._debounce.cancel()
            self._debounce = threading.Timer(0.35, self._debounced_emit)
            self._debounce.daemon = True
            self._debounce.start()

    def _debounced_emit(self) -> None:
        with self._lock:
            self._debounce = None
        self._emit(final=False)

    def _emit(self, *, final: bool) -> None:
        with self._lock:
            text = self._buf.strip()
            if not text or not self._on_reply:
                return
            if final:
                if self._final_sent and text == self._last_sent:
                    return
                self._final_sent = True
            else:
                if len(text) - len(self._last_sent) < 24 and not final:
                    return
                if text == self._last_sent:
                    return
            self._last_sent = text

        try:
            self._on_reply(text, final, self._meta)
        except TypeError:
            try:
                self._on_reply(text, final)
            except Exception:
                pass
        except Exception:
            pass


def set_active_token_fn(fn: Callable[[], str]) -> None:
    """Backward compat — no longer used (per-job tokens via opencode_jobs)."""
    del fn
