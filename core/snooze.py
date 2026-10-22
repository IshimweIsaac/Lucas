"""Snooze: reschedule a one-shot reminder via the existing reminder module."""

from __future__ import annotations

from datetime import datetime, timedelta

from actions.reminder import reminder


def schedule_snooze(minutes: int, message: str) -> str:
    if minutes < 1:
        return "Snooze must be at least 1 minute."
    when = datetime.now() + timedelta(minutes=minutes)
    return reminder(
        {
            "date": when.strftime("%Y-%m-%d"),
            "time": when.strftime("%H:%M"),
            "message": f"(Snoozed) {message}",
        }
    )
