"""
Unified API key manager with thread-safe round-robin rotation.

All agent keys live in ``config/agent_keys.json``::

    {
      "gemini": ["key1", "key2", "key3"],
      "groq":   ["key1", "key2"]
    }

Each call to ``get_key("gemini")`` returns the next key in rotation,
allowing parallel agents to spread load across multiple keys.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

_KEYS_FILE = get_base_dir() / "config" / "agent_keys.json"


class KeyManager:
    """Thread-safe round-robin API key provider."""

    def __init__(self, keys_file: Path | None = None):
        self._file = keys_file or _KEYS_FILE
        self._keys: dict[str, list[str]] = {}
        self._indices: dict[str, int] = {}
        self._lock = threading.Lock()
        self.reload()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """(Re)load keys from disk."""
        if not self._file.exists():
            logger.warning(
                "[KeyManager] %s not found — no agent keys loaded", self._file
            )
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            with self._lock:
                for provider in ("gemini", "groq", "openrouter"):
                    raw = data.get(provider, [])
                    keys = [k for k in raw if k and isinstance(k, str)]
                    self._keys[provider] = keys
                    # Preserve current index if within bounds, else reset
                    if provider not in self._indices or self._indices[provider] >= len(
                        keys
                    ):
                        self._indices[provider] = 0
            loaded = {p: len(k) for p, k in self._keys.items() if k}
            logger.info("[KeyManager] ✅ Loaded keys: %s", loaded)
        except Exception as exc:
            logger.error("[KeyManager] ❌ Failed to load keys: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_key(self, provider: str) -> str:
        """Return the next key for *provider* (round-robin)."""
        with self._lock:
            keys = self._keys.get(provider, [])
            if not keys:
                return ""
            idx = self._indices.get(provider, 0)
            key = keys[idx % len(keys)]
            self._indices[provider] = (idx + 1) % len(keys)
            return key

    def has_keys(self, provider: str) -> bool:
        with self._lock:
            return bool(self._keys.get(provider))

    def key_count(self, provider: str) -> int:
        with self._lock:
            return len(self._keys.get(provider, []))

    def provider_for_model(self, model: str) -> str:
        """Infer provider name from an Aider model string."""
        if model.startswith("gemini/"):
            return "gemini"
        if model.startswith("groq/"):
            return "groq"
        if model.startswith("openrouter/"):
            return "openrouter"
        return ""


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_instance: KeyManager | None = None
_instance_lock = threading.Lock()


def get_key_manager() -> KeyManager:
    """Return the global KeyManager singleton (lazy-init)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KeyManager()
    return _instance
