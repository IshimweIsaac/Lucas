"""File and directory watching via the watchdog library.

Supports starting, listing, and stopping observers that monitor
directories for file system events (create, modify, delete, move).
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional watchdog import
# ---------------------------------------------------------------------------
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_watchers: dict[str, Observer] = {}
_watcher_info: dict[str, dict] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------
class _LoggingHandler(FileSystemEventHandler):
    """Logs all file system events to the module logger."""

    def __init__(self, watcher_id: str, path: str, pattern: str) -> None:
        super().__init__()
        self._watcher_id = watcher_id
        self._path = path
        self._pattern = pattern

    def on_created(self, event) -> None:
        logger.info("[Watcher %s] Created: %s", self._watcher_id[:8], event.src_path)

    def on_modified(self, event) -> None:
        logger.info("[Watcher %s] Modified: %s", self._watcher_id[:8], event.src_path)

    def on_deleted(self, event) -> None:
        logger.info("[Watcher %s] Deleted: %s", self._watcher_id[:8], event.src_path)

    def on_moved(self, event) -> None:
        logger.info(
            "[Watcher %s] Moved: %s -> %s",
            self._watcher_id[:8],
            event.src_path,
            event.dest_path,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def watch_directory(path: str, pattern: str = "*", callback_action: str = "") -> str:
    """Start watching a directory for file changes.

    Args:
        path: Directory path to watch.
        pattern: Glob pattern (currently for display; all events are logged).
        callback_action: Placeholder for future callback support.

    Returns:
        Watcher ID string.
    """
    if not _WATCHDOG_AVAILABLE:
        return (
            "watchdog library is not installed. Install it with: pip install watchdog"
        )

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        return f"Directory not found: {path}"

    watcher_id = str(uuid.uuid4())
    event_handler = _LoggingHandler(watcher_id, str(resolved), pattern)
    observer = Observer()
    observer.schedule(event_handler, str(resolved), recursive=True)

    with _lock:
        _watchers[watcher_id] = observer
        _watcher_info[watcher_id] = {
            "path": str(resolved),
            "pattern": pattern,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "callback_action": callback_action,
        }

    observer.daemon = True
    observer.start()

    logger.info(
        "Started watcher %s for %s (pattern=%s)",
        watcher_id[:8],
        resolved,
        pattern,
    )
    return (
        f"Watching directory '{resolved}' for changes. "
        f"Watcher ID: {watcher_id[:8]}... Events are being logged."
    )


def list_watchers() -> str:
    """List all active file watchers."""
    with _lock:
        if not _watchers:
            return "No active file watchers."

        lines: list[str] = [f"Active file watchers ({len(_watchers)}):"]
        for wid, obs in list(_watchers.items()):
            info = _watcher_info.get(wid, {})
            short = wid[:8]
            path = info.get("path", "?")
            started = info.get("started", "?")
            alive = "running" if obs.is_alive() else "stopped"
            lines.append(f"  {short}... | {path} | {started} | {alive}")
        return "\n".join(lines)


def stop_watcher(watcher_id: str) -> str:
    """Stop a file watcher by its ID (full or prefix)."""
    if not watcher_id:
        return "Provide watcher_id= to stop."

    with _lock:
        # Match full ID or prefix
        matched = None
        for wid in list(_watchers.keys()):
            if wid == watcher_id or wid.startswith(watcher_id):
                matched = wid
                break

        if matched is None:
            return (
                f"No watcher found with ID '{watcher_id}'. "
                f"Use list_watchers to see active watchers."
            )

        observer = _watchers.pop(matched)
        _watcher_info.pop(matched, None)

    try:
        observer.stop()
        observer.join(timeout=3)
    except Exception as e:
        logger.error("Error stopping watcher %s: %s", matched[:8], e)
        return f"Error stopping watcher: {e}"

    logger.info("Stopped watcher %s", matched[:8])
    return f"Watcher {matched[:8]}... stopped."


def stop_all_watchers() -> str:
    """Stop all active file watchers."""
    with _lock:
        ids = list(_watchers.keys())

    if not ids:
        return "No active file watchers to stop."

    stopped = 0
    for wid in ids:
        result = stop_watcher(wid)
        if "stopped" in result.lower():
            stopped += 1

    return f"Stopped {stopped} watcher(s)."
