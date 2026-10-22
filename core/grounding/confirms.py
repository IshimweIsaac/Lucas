"""Destructive-action confirmation handshake.

Targets matching a destructive keyword require a two-call confirmation: the
first call registers a pending confirmation (TTL 60s, per-process registry);
the second identical call within the TTL proceeds. This prevents accidental
destructive clicks while staying stateless for the model (no new params).
"""

from __future__ import annotations

import re
import threading
import time

_CONFIRM_TTL_SEC = 60.0

_DESTRUCTIVE_KEYWORDS = (
    "delete",
    "remove",
    "clear",
    "send",
    "submit",
    "pay",
    "purchase",
    "buy",
    "close tab",
    "quit",
    "shut down",
    "restart",
    "format",
    "wipe",
    "uninstall",
)

_DESTRUCTIVE_RE = re.compile(r"close\s+.*tab", re.IGNORECASE)

_pending_confirms: dict[str, float] = {}
_lock = threading.Lock()


def is_destructive(target: str) -> bool:
    """True when *target* matches a destructive-action keyword (v1 hardcoded)."""
    t = (target or "").strip().lower()
    if not t:
        return False
    if any(keyword in t for keyword in _DESTRUCTIVE_KEYWORDS):
        return True
    return bool(_DESTRUCTIVE_RE.search(t))


def confirm_required(target: str) -> bool:
    """Register/consume the confirmation for *target*.

    Returns True when the caller must ask for confirmation (no pending entry
    or TTL expired), False when the call is confirmed and may proceed.
    """
    now = time.monotonic()
    with _lock:
        due = _pending_confirms.get(target)
        if due is None or now > due:
            _pending_confirms[target] = now + _CONFIRM_TTL_SEC
            return True
        _pending_confirms.pop(target, None)
        return False


def clear_pending_confirmations() -> None:
    """Drop all pending confirmations (used by tests)."""
    with _lock:
        _pending_confirms.clear()
