"""
Unified task history for all agent operations.

Persists to ``memory/agent_history.json``.  Replaces the per-tool
history scattered across aider_agent.py, etc.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

_HISTORY_FILE = get_base_dir() / "memory" / "agent_history.json"
_MAX_ENTRIES = 50


class TaskHistory:
    """Thread-safe, disk-backed task history."""

    def __init__(self, history_file: Path | None = None):
        self._file = history_file or _HISTORY_FILE
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------

    def load(self) -> list[dict]:
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, entries: list[dict]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(entries[-_MAX_ENTRIES:], indent=2, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, entry: dict) -> None:
        """Append an entry and persist."""
        with self._lock:
            entries = self.load()
            entries.append(entry)
            self._save(entries)

    def recent(self, n: int = 10) -> list[dict]:
        """Return the *n* most recent entries."""
        with self._lock:
            return self.load()[-n:]

    def find(self, task_id: str) -> dict | None:
        """Find an entry by task_id."""
        with self._lock:
            for entry in reversed(self.load()):
                if entry.get("task_id") == task_id:
                    return entry
        return None

    def latest(self) -> dict | None:
        """Return the most recent entry."""
        with self._lock:
            entries = self.load()
            return entries[-1] if entries else None

    @staticmethod
    def make_id(prefix: str = "agent") -> str:
        """Generate a unique task ID."""
        return f"{prefix}_{int(time.time())}"

    @staticmethod
    def make_entry(
        *,
        task_id: str,
        agent: str,
        prompt: str,
        workspace: str,
        model: str,
        status: str = "started",
        **extra,
    ) -> dict:
        """Build a standard history entry dict."""
        return {
            "task_id": task_id,
            "agent": agent,
            "prompt": prompt,
            "workspace": workspace,
            "model": model,
            "status": status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            **extra,
        }
