"""WebSocket bridge between Lucas backend and lucas_ui (React/Electron web UI).

Provides:
- WebSocketServer: asyncio WebSocket server on port 8765
- WebSocketPlayer: drop-in replacement for LucasUI that sends JSON over WebSocket

Tools receive WebSocketPlayer as ``player`` and call the same methods — zero changes needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
import re
import time
from typing import Any, Callable

import websockets
from websockets.http11 import Request as WSRequest
from websockets.http11 import Response as WSResponse

from core.daily_todo_store import (
    list_todos,
    stats as todo_stats,
    on_change as todo_on_change,
    add_todo as todo_add,
    toggle_todo as todo_toggle,
    delete_todo as todo_delete,
    archive_done as todo_archive_done,
)
from memory import semantic_memory

logger = logging.getLogger(__name__)

WS_PORT = 8765


def _coerce_memory_list_payload(payload: Any) -> tuple[str, int, int]:
    """Defensively coerce a memory.list payload to (query, limit, offset).

    Malformed payloads fall back to defaults instead of raising.
    """
    if not isinstance(payload, dict):
        return "", 100, 0
    query = str(payload.get("query") or "")
    try:
        limit = int(payload.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = int(payload.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    return query, limit, offset


def _valid_memory_id(payload: Any) -> int | None:
    """Extract a usable integer id from a payload dict, else None.

    Bools are ints in Python but are never valid row ids.
    """
    if not isinstance(payload, dict):
        return None
    id_val = payload.get("id")
    if isinstance(id_val, bool) or not isinstance(id_val, int):
        return None
    return id_val


class WebSocketPlayer:
    """Drop-in replacement for LucasUI that sends messages over WebSocket.

    Mirrors the full public interface of LucasUI so existing tools work unchanged.
    Each method serialises a JSON message and queues it for delivery to all
    connected web UI clients.
    """

    def __init__(self, server: WebSocketServer) -> None:
        self._server = server
        server._player = self
        self._muted = False
        self._screen_watch = False
        self.on_text_command: Callable[[str], Any] | None = None
        self.on_screen_watch_changed: Callable[[bool], Any] | None = None

    # ── properties ──────────────────────────────────────────────────────

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, v: bool) -> None:
        if v != self._muted:
            self._muted = v
            self._server.send({
                "type": "status.update",
                "payload": {"mic": "muted" if v else "live"},
            })

    @property
    def screen_watch(self) -> bool:
        return self._screen_watch

    @screen_watch.setter
    def screen_watch(self, v: bool) -> None:
        if v != self._screen_watch:
            self._screen_watch = v
            self._server.send({
                "type": "status.update",
                "payload": {"watch": "active" if v else "inactive"},
            })
            if self.on_screen_watch_changed is not None:
                self.on_screen_watch_changed(v)

    @property
    def current_file(self) -> str | None:
        return None

    # ── core UI methods ─────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        self._server.send({
            "type": "connection.state",
            "payload": {"state": state.upper()},
        })

    def write_log(self, text: str) -> None:
        level = self._infer_log_level(text)
        message = self._strip_prefix(text)
        self._server.send({
            "type": "log.entry",
            "payload": {"level": level, "message": message},
        })

    def run_on_main_thread(self, fn: Callable) -> None:
        """Schedule work on the asyncio event loop (analogue of Qt's main thread)."""
        loop = self._server._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(fn)

    def speak(self, text: str) -> None:
        """Called when Lucas speaks — sends a transcript message to the UI."""
        self._server.send({
            "type": "chat.transcript",
            "payload": {"role": "assistant", "text": text, "is_final": True},
        })

    def start_speaking(self) -> None:
        self.set_state("SPEAKING")

    def stop_speaking(self) -> None:
        if not self._muted:
            self.set_state("LISTENING")

    # ── presentation ────────────────────────────────────────────────────

    def _render_presentation(
        self,
        title: str,
        body: str,
        *,
        format: str = "auto",
        slides: bool = False,
        slide: int = 0,
        rich_issues: bool = False,
    ) -> dict[str, Any]:
        """Pre-render presentation slides and return a payload dict.

        Each slide is a full HTML document. We extract the body content
        and the shared CSS for the frontend to reconstruct.
        """
        try:
            from core.presentation.presentation_markup import build_render
        except ImportError:
            logger.warning("presentation_markup not available; skipping render")
            return {"title": title, "slide_css": "", "slide_bodies": [body or ""], "slide_labels": [], "slide_index": 0, "slide_count": 1}
        render = build_render(
            title=title or "Briefing",
            body=body or "",
            format=format or "auto",
            slides=bool(slides),
            slide=int(slide or 0),
            rich_issues=bool(rich_issues),
        )
        # Extract shared CSS from first slide
        slide_css = ""
        if render.slides:
            m = re.search(r"<style>(.*?)</style>", render.slides[0], re.DOTALL)
            if m:
                slide_css = m.group(1)
        # Extract body content from each slide
        slide_bodies: list[str] = []
        for s in render.slides:
            m = re.search(r"<body[^>]*>(.*)</body>", s, re.DOTALL)
            slide_bodies.append(m.group(1) if m else s)
        return {
            "title": render.title,
            "slide_css": slide_css,
            "slide_bodies": slide_bodies,
            "slide_labels": render.slide_labels,
            "slide_index": render.slide_index,
            "slide_count": render.slide_count,
        }

    def open_presentation(
        self,
        title: str,
        body: str,
        *,
        format: str = "auto",
        slides: bool = False,
        slide: int = 0,
        rich_issues: bool = False,
        window: str = "presentation",
    ) -> None:
        data = self._render_presentation(
            title=title, body=body, format=format,
            slides=slides, slide=slide, rich_issues=rich_issues,
        )
        self._server.send({
            "type": "window.open",
            "payload": {
                "window": window,
                "data": data,
            },
        })

    def update_presentation(
        self,
        body: str,
        *,
        title: str = "",
        format: str = "auto",
        slides: bool = False,
        slide: int = 0,
        rich_issues: bool = False,
        window: str = "presentation",
    ) -> None:
        data = self._render_presentation(
            title=title or "", body=body, format=format,
            slides=slides, slide=slide, rich_issues=rich_issues,
        )
        self._server.send({
            "type": "window.command",
            "payload": {
                "window": window,
                "command": "update",
                "data": data,
            },
        })

    def close_presentation(self, window: str = "presentation") -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": window},
        })

    def advance_presentation_slide(self, delta: int, window: str = "presentation") -> str:
        self._server.send({
            "type": "window.command",
            "payload": {
                "window": window,
                "command": "advance",
                "delta": delta,
            },
        })
        return str(delta)

    def open_presentation_slides(
        self, presentation: dict, window: str = "presentation"
    ) -> None:
        """Open a presentation from a pre-built payload dict.

        The dict must have keys: title, slide_css, slide_bodies,
        slide_labels, slide_index, slide_count — as produced by
        core.presentation_core.build_presentation().

        *window* selects which presentation window the UI targets, which
        allows several presentations to stay open at once.
        """
        self._server.send({
            "type": "window.open",
            "payload": {
                "window": window,
                "data": presentation,
            },
        })

    # ── daily todo ──────────────────────────────────────────────────────

    def open_daily_todo(self) -> None:
        data = self._get_todo_data()
        self._server.send({
            "type": "window.open",
            "payload": {"window": "daily-todo", "data": data},
        })

    def close_daily_todo(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "daily-todo"},
        })

    def refresh_daily_todo(self) -> None:
        data = self._get_todo_data()
        self._server.send({
            "type": "window.refresh",
            "payload": {"window": "daily-todo", "data": data},
        })

    def get_daily_todo_bridge(self) -> Any:
        return None

    # ── daily todo helpers ──────────────────────────────────────────────

    @staticmethod
    def _get_todo_data() -> dict[str, Any]:
        """Fetch current todos + stats from the backend store."""
        return {
            "todos": list_todos(),
            "stats": todo_stats(),
        }

    @staticmethod
    def _get_todo_stats() -> dict[str, Any]:
        return todo_stats()

    def _setup_todo_listener(self) -> None:
        """Push updated todo data to the frontend when the store changes."""
        def _push() -> None:
            self._server.send({
                "type": "todo.data",
                "payload": self._get_todo_data(),
            })
        todo_on_change(_push)

    # ── memories browser ────────────────────────────────────────────────

    def open_memories(self, payload: dict | None = None) -> None:
        """Open the Memories window; the view self-fetches via memory.list."""
        self._server.send({
            "type": "window.open",
            "payload": {"window": "memories", "data": payload or {}},
        })

    def close_memories(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "memories"},
        })

    # ── calendar ────────────────────────────────────────────────────────

    def open_calendar(self, payload: dict) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {"window": "calendar", "data": payload},
        })

    def close_calendar(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "calendar"},
        })

    # ── project window ──────────────────────────────────────────────────

    def open_project_window(self, project_id: str = "") -> None:
        self._server.send({
            "type": "window.open",
            "payload": {
                "window": "project",
                "data": {"project_id": project_id},
            },
        })

    def close_project_window(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "project"},
        })

    def get_project_bridge(self) -> Any:
        return None

    # ── coding environment ──────────────────────────────────────────────

    def open_coding_environment(self, folder: str = "", file_path: str = "") -> None:
        self._server.send({
            "type": "window.open",
            "payload": {
                "window": "coding",
                "data": {"folder": folder, "file_path": file_path},
            },
        })

    def close_coding_environment(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "coding"},
        })

    def get_coding_bridge(self) -> Any:
        return None

    def run_coding_js(self, code: str) -> None:
        self._server.send({
            "type": "window.command",
            "payload": {
                "window": "coding",
                "command": "run_js",
                "data": {"code": code},
            },
        })

    # ── learning ────────────────────────────────────────────────────────

    def open_learning(self, payload: dict) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {"window": "learning", "data": payload},
        })

    def close_learning(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "learning"},
        })

    def learning_command(self, command: str, params: dict | None = None) -> None:
        self._server.send({
            "type": "window.command",
            "payload": {
                "window": "learning",
                "command": command,
                "data": params or {},
            },
        })

    # ── github ──────────────────────────────────────────────────────────

    def open_github_window(self) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {"window": "github"},
        })

    def close_github_window(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "github"},
        })

    def get_github_bridge(self) -> Any:
        return None

    # ── opencode ────────────────────────────────────────────────────────

    def open_opencode_window(self) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {"window": "opencode"},
        })

    def close_opencode_window(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "opencode"},
        })

    # ── word processor ──────────────────────────────────────────────────

    def open_word_processor(self, payload: dict) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {"window": "word-processor", "data": payload},
        })

    def close_word_processor(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "word-processor"},
        })

    # ── youtube ─────────────────────────────────────────────────────────

    def open_youtube_player(
        self,
        video_id: str = "",
        query: str = "",
        title: str = "",
    ) -> None:
        self._server.send({
            "type": "window.open",
            "payload": {
                "window": "youtube",
                "data": {
                    "video_id": video_id,
                    "query": query,
                    "title": title,
                },
            },
        })

    def close_youtube_player(self) -> None:
        self._server.send({
            "type": "window.close",
            "payload": {"window": "youtube"},
        })

    def youtube_control(self, action: str, **params: Any) -> None:
        self._server.send({
            "type": "window.command",
            "payload": {
                "window": "youtube",
                "command": action,
                "data": params,
            },
        })

    # ── helpers ─────────────────────────────────────────────────────────

    def wait_for_api_key(self) -> None:
        pass  # No API key input in web UI yet

    def set_metrics(self, cpu: float, mem: dict, disk: dict, temp: float,
                    uptime: float, platform: str, load: list[float],
                    battery: dict | None = None) -> None:
        """Send system metrics to the web UI."""
        self._server.send({
            "type": "metrics.update",
            "payload": {
                "cpu": cpu,
                "mem": mem,
                "disk": disk,
                "temp": temp,
                "uptime": uptime,
                "platform": platform,
                "load": load,
                "battery": battery,
            },
        })

    def update_feed(self, feed_type: str, items: list[dict]) -> None:
        """Send feed updates (reminders, tasks, alerts) to the web UI."""
        self._server.send({
            "type": "feed.update",
            "payload": {"type": feed_type, "items": items},
        })

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _infer_log_level(text: str) -> str:
        upper = text.upper()
        if "ERROR" in upper:
            return "error"
        if "WARN" in upper or "⚠" in text:
            return "warn"
        if "SUCCESS" in upper or "✅" in text or "✔" in text:
            return "success"
        if "DEBUG" in upper:
            return "debug"
        return "info"

    @staticmethod
    def _strip_prefix(text: str) -> str:
        prefixes = ["SYS: ", "GUARD: ", "BLOCK: ", "AUTO-REDIRECT "]
        for p in prefixes:
            if text.startswith(p):
                return text[len(p):]
        return text


class WebSocketServer:
    """Manages the WebSocket server and connected web UI clients.

    Runs inside the existing asyncio event loop alongside Gemini Live.
    Thread-safe: any thread can call ``send()`` — it schedules the write
    on the event loop via ``asyncio.run_coroutine_threadsafe``.
    """

    def __init__(
        self,
        player: WebSocketPlayer | None = None,
        host: str = "localhost",
        port: int = WS_PORT,
    ) -> None:
        self._player = player
        self._host = host
        self._port = port
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: websockets.WebSocketServer | None = None
        # Last memory.list request context — post-mutation broadcasts reuse it
        # so a filtered/paged browser view stays consistent.
        self._last_memory_list: dict[str, Any] = {"query": "", "limit": 100, "offset": 0}
        if player is not None:
            player._setup_todo_listener()

    async def start(self) -> None:
        """Start the WebSocket server.

        Must be called from the asyncio loop.
        """
        self._loop = asyncio.get_running_loop()
        # Start the WebSocket server
        self._server = await websockets.serve(
            self._handle_client,
            self._host,
            self._port,
            ping_interval=30,
            ping_timeout=10,
            max_size=2 ** 20,  # 1 MB max message
            process_request=self._reject_plain_http,
        )
        logger.info("WebSocket server listening on ws://%s:%s", self._host, self._port)

    @staticmethod
    async def _reject_plain_http(
        _connection_or_path: object,
        _headers_or_request: object,
    ) -> WSResponse | None:
        """Return 400 for non-WebSocket requests to avoid traceback noise.

        Handles both websockets <14 (path, headers) and >=14 (connection, Request).
        """
        if isinstance(_headers_or_request, WSRequest):
            # websockets >=14: second arg is a Request object with .headers
            upgrade = _headers_or_request.headers.get("Upgrade", "")
        else:
            # websockets <14: second arg is the headers dict directly
            upgrade = _headers_or_request.get("Upgrade", "")  # type: ignore[union-attr]
        if upgrade.lower() != "websocket":
            return WSResponse(400, "Bad Request", {}, b"Bad Request")
        return None

    async def stop(self) -> None:
        """Stop the server and disconnect all clients."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for client in self._clients.copy():
            await client.close()
        self._clients.clear()

    async def _handle_client(
        self, websocket: websockets.WebSocketServerProtocol,
    ) -> None:
        """Handle an individual WebSocket client connection."""
        self._clients.add(websocket)
        logger.info("Web UI client connected (%d total)", len(self._clients))
        try:
            await self._send_to(websocket, {
                "type": "connection.status",
                "payload": {"status": "connected"},
            })
            await self._send_to(websocket, {
                "type": "connection.state",
                "payload": {"state": "INITIALISING"},
            })

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    await self._dispatch(msg, src=websocket)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from client: %s", raw[:200])

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("Web UI client disconnected (%d remaining)", len(self._clients))

    async def _dispatch(self, msg: dict, src: websockets.WebSocketServerProtocol | None = None) -> None:
        """Route an incoming message to the right handler.

        ``src`` is the websocket that sent the message — used for
        request/response patterns like ``github.invoke``.
        """
        msg_type = msg.get("type")
        payload = msg.get("payload", {})

        if msg_type == "command.send":
            text = payload.get("text", "")
            if text and self._player.on_text_command is not None:
                self._player.on_text_command(text)

        elif msg_type == "command.toggle_mute":
            self._player.muted = not self._player.muted
            logger.info("Mute toggled (muted=%s)", self._player.muted)

        elif msg_type == "command.toggle_watch":
            if not self._player.screen_watch:
                # v1: Screen Watch live streaming is not wired — soft-disconnect.
                self.send({"type": "status.update", "payload": {"watch": "inactive"}})
                logger.info("Screen Watch live streaming not wired in this build (v1)")
            else:
                self._player.screen_watch = False
                logger.info("Screen watch off (watch=%s)", self._player.screen_watch)

        elif msg_type == "command.clear_chat":
            self.send({"type": "chat.cleared", "payload": {}})

        elif msg_type == "command.toggle_fullscreen":
            logger.info("Fullscreen toggle received (not yet implemented in web)")

        elif msg_type == "heartbeat":
            await self._broadcast({
                "type": "heartbeat",
                "payload": {"ts": time.time()},
            })

        # ── daily todo CRUD ─────────────────────────────────────────────
        elif msg_type == "todo.get_all":
            await self._broadcast({
                "type": "todo.data",
                "payload": {
                    "todos": list_todos(),
                    "stats": todo_stats(),
                },
            })

        elif msg_type == "todo.add":
            title = payload.get("title", "").strip()
            priority = payload.get("priority", "p2")
            section = payload.get("section", "morning")
            if title:
                todo_add(title, priority=priority, section=section)
            # The on_change listener will push the updated data automatically

        elif msg_type == "todo.toggle":
            todo_id = payload.get("todo_id", "")
            if todo_id:
                todo_toggle(todo_id)

        elif msg_type == "todo.delete":
            todo_id = payload.get("todo_id", "")
            if todo_id:
                todo_delete(todo_id)

        elif msg_type == "todo.archive_done":
            todo_archive_done()

        # ── memories browser CRUD ────────────────────────────────────────
        elif msg_type == "memory.list":
            query, limit, offset = _coerce_memory_list_payload(payload)
            self._last_memory_list = {"query": query, "limit": limit, "offset": offset}
            await self._broadcast_memory_data(query, limit, offset)

        elif msg_type == "memory.delete":
            mid = _valid_memory_id(payload)
            if mid is None:
                await self._broadcast_memory_result({
                    "ok": False,
                    "id": None,
                    "error": "invalid or missing memory id",
                })
            else:
                ok = False
                error = ""
                try:
                    ok = await asyncio.to_thread(semantic_memory.delete_memory, mid)
                except Exception as e:
                    logger.warning("memory.delete failed: %s", e)
                    error = "delete failed"
                if ok:
                    result_payload: dict[str, Any] = {"ok": True, "id": mid}
                else:
                    result_payload = {
                        "ok": False,
                        "id": mid,
                        "error": error or "no such memory",
                    }
                await self._broadcast_memory_result(result_payload)
                if ok:
                    ctx = self._last_memory_list
                    await self._broadcast_memory_data(
                        str(ctx.get("query") or ""),
                        int(ctx.get("limit", 100)),
                        int(ctx.get("offset", 0)),
                    )

        elif msg_type == "memory.update":
            mid = _valid_memory_id(payload)
            text_val = payload.get("text") if isinstance(payload, dict) else None
            if mid is None:
                await self._broadcast_memory_result({
                    "ok": False,
                    "id": None,
                    "error": "invalid or missing memory id",
                })
            elif not isinstance(text_val, str) or not text_val.strip():
                await self._broadcast_memory_result({
                    "ok": False,
                    "id": mid,
                    "error": "text must be a non-empty string",
                })
            else:
                ok = False
                error = ""
                try:
                    ok = await asyncio.to_thread(semantic_memory.update_text, mid, text_val)
                except Exception as e:
                    logger.warning("memory.update failed: %s", e)
                    error = "update failed (embed error or row missing)"
                if ok:
                    result_payload = {"ok": True, "id": mid}
                else:
                    result_payload = {
                        "ok": False,
                        "id": mid,
                        "error": error or "update failed (embed error or row missing)",
                    }
                await self._broadcast_memory_result(result_payload)
                if ok:
                    ctx = self._last_memory_list
                    await self._broadcast_memory_data(
                        str(ctx.get("query") or ""),
                        int(ctx.get("limit", 100)),
                        int(ctx.get("offset", 0)),
                    )

        # ── word processor ──────────────────────────────────────────────
        elif msg_type == "word.save":
            html = payload.get("html", "")
            title = payload.get("title", "Untitled")
            path = payload.get("path") or os.path.expanduser(
                f"~/Documents/Lucas/{title}.html"
            )
            await asyncio.to_thread(os.makedirs, os.path.dirname(path), exist_ok=True)
            await asyncio.to_thread(lambda: open(path, "w", encoding="utf-8").write(html))
            logger.info("Word processor saved to %s", path)
            if src is not None:
                await self._send_to(src, {
                    "type": "word.saved",
                    "payload": {"path": path, "title": title},
                })

        elif msg_type == "word.save_as":
            html = payload.get("html", "")
            title = payload.get("title", "Untitled")
            filename = payload.get("filename", f"{title}.html")
            save_dir = os.path.expanduser("~/Documents/Lucas")
            await asyncio.to_thread(os.makedirs, save_dir, exist_ok=True)
            path = os.path.join(save_dir, filename)
            await asyncio.to_thread(lambda: open(path, "w", encoding="utf-8").write(html))
            logger.info("Word processor saved as %s", path)
            if src is not None:
                await self._send_to(src, {
                    "type": "word.saved",
                    "payload": {"path": path, "title": title},
                })

        elif msg_type == "word.open":
            path = payload.get("path", "") or os.path.expanduser("~/Documents/Lucas")
            if os.path.isdir(path):
                # Folder — list files
                try:
                    files = sorted([
                        f for f in os.listdir(path)
                        if f.endswith(('.html', '.docx', '.md'))
                    ])
                except OSError:
                    logger.warning("Could not list word processor files in %s", path)
                    files = []
                await self._broadcast(json.dumps({
                    "type": "window.refresh",
                    "payload": {
                        "window": "word-processor",
                        "data": {"files": files, "folder": path},
                    },
                }))
            elif os.path.isfile(path):
                # File — read and push content
                try:
                    content = await asyncio.to_thread(
                        lambda: open(path, "r", encoding="utf-8").read()
                    )
                    await self._broadcast(json.dumps({
                        "type": "window.refresh",
                        "payload": {
                            "window": "word-processor",
                            "data": {
                                "html": content,
                                "title": os.path.splitext(os.path.basename(path))[0],
                                "path": path,
                            },
                        },
                    }))
                except OSError:
                    logger.warning("Could not read word processor file: %s", path)

        # ── window refresh stubs (push placeholder data) ──────────────
        elif msg_type == "github.refresh":
            logger.info("GitHub refresh requested (stub)")
            self.send({
                "type": "window.refresh",
                "payload": {"window": "github", "data": {}},
            })

        elif msg_type == "coding.refresh":
            logger.info("Coding refresh requested (stub)")
            self.send({
                "type": "window.refresh",
                "payload": {"window": "coding", "data": {}},
            })

        elif msg_type == "project.refresh":
            logger.info("Project refresh requested (stub)")
            self.send({
                "type": "window.refresh",
                "payload": {"window": "project", "data": {}},
            })

    async def _broadcast_memory_data(self, query: str, limit: int, offset: int) -> None:
        """Read fresh rows from the store and broadcast a memory.data message.

        Never raises: on failure it degrades to an empty snapshot so no
        traceback can reach the client socket.
        """
        try:
            memories = await asyncio.to_thread(
                semantic_memory.list_memories, query, limit, offset
            )
            total = await asyncio.to_thread(semantic_memory.count_memories, query)
            payload: dict[str, Any] = {"memories": memories, "total": total, "query": query}
        except Exception as e:
            logger.warning("memory.data read failed: %s", e)
            payload = {"memories": [], "total": 0, "query": query}
        await self._broadcast({"type": "memory.data", "payload": payload})

    async def _broadcast_memory_result(self, payload: dict[str, Any]) -> None:
        """Broadcast an ack/failure memory.result for delete/update."""
        await self._broadcast({"type": "memory.result", "payload": payload})

    def send(self, msg: dict) -> None:
        """Thread-safe send to all connected clients.

        Can be called from any thread (including the thread pool where
        tool handlers run).  Schedules the actual write on the asyncio
        event loop.
        """
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._broadcast(json.dumps(msg, default=str)),
                self._loop,
            )

    async def _broadcast(self, data: str) -> None:
        """Send *data* to every connected client (must be on the event loop)."""
        if not self._clients:
            return
        await asyncio.gather(
            *(self._send_to(c, data) for c in self._clients.copy()),
            return_exceptions=True,
        )

    @staticmethod
    async def _send_to(
        websocket: websockets.WebSocketServerProtocol,
        data: str | dict,
    ) -> None:
        if isinstance(data, dict):
            data = json.dumps(data, default=str)
        try:
            await websocket.send(data)
        except websockets.exceptions.ConnectionClosed:
            pass
