"""GNOME notification history for Lucas — send notifications and track history."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from core.pc_control import _run

logger = get_logger(__name__)

_NOTIFICATION_LOG = Path.home() / ".lucas" / "notifications.jsonl"
_MAX_HISTORY = 100
_URGENCY_LEVELS = {"low": "low", "normal": "normal", "critical": "critical"}


def send_notification(title: str, body: str, urgency: str = "normal") -> str:
    """Send a desktop notification.

    Uses notify-send. Urgency: low, normal, critical.
    """
    if not title:
        return "Provide a title for the notification."
    if not body:
        return "Provide a body for the notification."

    urgency = urgency.lower() if urgency.lower() in _URGENCY_LEVELS else "normal"

    if not shutil.which("notify-send"):
        return (
            "notify-send not available. Install libnotify (sudo dnf install libnotify)."
        )

    r = _run(
        ["notify-send", "-u", urgency, title, body],
        timeout=5,
    )
    if r.ok:
        _log_notification(title, body, urgency)
        return f"Notification sent: {title}"
    return f"Failed to send notification: {r.stderr or 'unknown error'}"


def _log_notification(title: str, body: str, urgency: str) -> None:
    """Log a notification to the local tracking file."""
    try:
        _NOTIFICATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "body": body,
            "urgency": urgency,
        }
        with _NOTIFICATION_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        # Trim old entries
        _trim_log()
    except OSError as exc:
        logger.warning("Failed to log notification: %s", exc)


def _trim_log() -> None:
    """Keep only the last _MAX_HISTORY entries in the log file."""
    try:
        if not _NOTIFICATION_LOG.exists():
            return
        with _NOTIFICATION_LOG.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= _MAX_HISTORY:
            return
        with _NOTIFICATION_LOG.open("w", encoding="utf-8") as f:
            f.writelines(lines[-_MAX_HISTORY:])
    except OSError as exc:
        logger.warning("Failed to trim notification log: %s", exc)


def get_recent_notifications(limit: int = 10) -> str:
    """Get recent notification history from the local tracking file.

    Args:
        limit: Maximum number of recent notifications to return (default 10).
    """
    try:
        if not _NOTIFICATION_LOG.exists():
            return "No notifications have been sent this session."
        with _NOTIFICATION_LOG.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            return "No notifications logged yet."
        entries = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "?")[:19]
                title = entry.get("title", "?")
                body = entry.get("body", "")
                urgency = entry.get("urgency", "normal")
                entries.append(f"[{ts}] ({urgency}) {title}: {body[:80]}")
            except (json.JSONDecodeError, KeyError):
                continue
        if not entries:
            return "No valid notification entries found."
        return "Recent Notifications:\n" + "\n".join(f"  {e}" for e in entries)
    except OSError as exc:
        return f"Failed to read notification history: {exc}"
