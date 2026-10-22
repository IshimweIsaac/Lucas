"""Subscribe to OpenCode server SSE events for live UI tracking."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from core.logger import get_logger
from core.opencode.opencode_client import OpenCodeClient

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], None]

# Dropped before UI callbacks — boot noise, not agent work
_SKIP_EVENT_TYPES = frozenset({
    "server.heartbeat",
    "plugin.added",
    "plugin.removed",
    "reference.updated",
    "session.updated",
    "session.next.agent.switched",
    "session.next.model.switched",
    "lsp.updated",
    "mcp.server.connected",
    "mcp.log",
})


def _parse_sse_chunk(buffer: str) -> tuple[list[dict[str, Any]], str]:
    """Parse SSE ``data:`` lines from a growing buffer."""
    events: list[dict[str, Any]] = []
    while "\n\n" in buffer:
        block, buffer = buffer.split("\n\n", 1)
        data_lines = [
            ln[5:].strip()
            for ln in block.splitlines()
            if ln.startswith("data:")
        ]
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        if raw in ("", "[DONE]"):
            continue
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                events.append(payload)
        except json.JSONDecodeError:
            continue
    return events, buffer


class EventSubscriber:
    """Background SSE reader filtered to one session."""

    def __init__(
        self,
        client: OpenCodeClient,
        *,
        session_id: str = "",
        on_event: EventCallback | None = None,
    ):
        self._client = client
        self._session_id = (session_id or "").strip()
        self._on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._done = threading.Event()  # SSE stream ended (any reason)
        self._error: str = ""
        self._part_text: dict[str, str] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._idle.clear()
        self._done.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="oc_events")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def wait_idle(self, timeout: float = 600) -> bool:
        if self._idle.wait(timeout=timeout):
            return True
        return False

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Wait for session.idle or SSE stream end, indefinitely by default.

        Returns True if idle received, False if SSE stream ended without idle.
        """
        remaining = timeout if timeout is not None else float("inf")
        while remaining > 0:
            chunk = min(remaining, 30.0)
            t0 = time.time()
            if self._idle.wait(timeout=chunk):
                return True
            if self._done.is_set():
                return False
            remaining -= time.time() - t0
        return False

    @property
    def error(self) -> str:
        return self._error

    @property
    def sse_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._done.is_set()

    def _emit(self, event_type: str, props: dict[str, Any]) -> None:
        if self._on_event:
            try:
                self._on_event(event_type, props)
            except Exception as exc:
                logger.debug("[opencode_events] callback: %s", exc)

    def _session_match(self, props: dict[str, Any]) -> bool:
        if not self._session_id:
            return True
        sid = (
            props.get("sessionID")
            or props.get("sessionId")
            or props.get("session_id")
            or ""
        )
        if sid and str(sid) != self._session_id:
            info = props.get("info") or {}
            part = props.get("part") or {}
            if isinstance(info, dict):
                sid = sid or info.get("sessionID") or ""
            if isinstance(part, dict):
                sid = sid or part.get("sessionID") or ""
            if sid and str(sid) != self._session_id:
                return False
        return True

    def _handle(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("type") or payload.get("event") or "")
        props = payload.get("properties") or payload.get("data") or payload
        if not isinstance(props, dict):
            props = {"value": props}

        if not self._session_match(props):
            return

        if event_type not in _SKIP_EVENT_TYPES:
            self._emit(event_type, props)

        if event_type in ("session.idle", "session.status"):
            status = props.get("status")
            if event_type == "session.idle" or status == "idle":
                self._idle.set()

        if event_type == "session.error":
            self._error = str(props.get("message") or props.get("error") or "session error")
            self._idle.set()

        if event_type == "message.part.updated":
            part = props.get("part") or {}
            if isinstance(part, dict):
                pid = str(part.get("id") or part.get("messageID") or "")
                delta = props.get("delta")
                if delta and pid:
                    self._part_text[pid] = self._part_text.get(pid, "") + str(delta)

    def _run(self) -> None:
        paths = ("/event", "/global/event")
        for path in paths:
            if self._stop.is_set():
                break
            if self._stream_path(path):
                break
        self._done.set()
        if not self._idle.is_set() and self._error:
            logger.warning("[opencode_events] SSE ended without idle: %s", self._error)

    def _stream_path(self, path: str) -> bool:
        url = f"{self._client.base_url}{path}"
        req = urllib.request.Request(url, method="GET", headers={"Accept": "text/event-stream"})
        if self._client.password:
            import base64

            token = base64.b64encode(
                f"{self._client.username}:{self._client.password}".encode()
            ).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")

        max_retries = 3
        for attempt in range(max_retries):
            if self._stop.is_set():
                return False
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    buf = ""
                    while not self._stop.is_set():
                        chunk = resp.read(4096)
                        if not chunk:
                            break
                        buf += chunk.decode("utf-8", errors="replace")
                        events, buf = _parse_sse_chunk(buf)
                        for ev in events:
                            self._handle(ev)
                    return True
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return False
                logger.debug("[opencode_events] %s HTTP %s (attempt %d/%d)", path, exc.code, attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue
            except Exception as exc:
                logger.debug("[opencode_events] %s: %s (attempt %d/%d)", path, exc, attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue
        return False


def wait_session_idle(
    client: OpenCodeClient,
    session_id: str,
    *,
    timeout: float = 600,
    poll_sec: float = 0.75,
    token: str = "",
) -> bool:
    """Poll ``GET /session/status`` until session is idle or timeout.

    If *token* is provided, exits early when the job is cancelled.
    """
    deadline = time.time() + timeout if timeout is not None else float("inf")
    sid = (session_id or "").strip()
    while time.time() < deadline:
        if token:
            from core.opencode import opencode_jobs as oc_jobs

            if not oc_jobs.is_token_active(token):
                return False
        try:
            status_map = client.session_status() or {}
            entry = status_map.get(sid) if isinstance(status_map, dict) else None
            if isinstance(entry, dict) and entry.get("status") == "idle":
                return True
            if isinstance(entry, str) and entry == "idle":
                return True
            if isinstance(status_map, dict) and status_map.get("status") == "idle":
                return True
        except Exception:
            pass
        time.sleep(poll_sec)
    return False
