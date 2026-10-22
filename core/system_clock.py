"""Local system date/time — used when voice must not guess from stale prompt context."""

from __future__ import annotations

from datetime import datetime


def now_local() -> datetime:
    return datetime.now().astimezone()


def format_datetime() -> str:
    now = now_local()
    return (
        f"Current time: {now.strftime('%I:%M %p')} ({now.strftime('%H:%M:%S')} 24h). "
        f"Date: {now.strftime('%A, %B %d, %Y')}."
    )


def format_time() -> str:
    now = now_local()
    return f"Current time: {now.strftime('%I:%M %p')} ({now.strftime('%H:%M:%S')} 24h)."


def format_date() -> str:
    now = now_local()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."


def format_connect_banner() -> str:
    """Single line for Live system instruction at connect."""
    now = now_local()
    return now.strftime("%A, %B %d, %Y — %I:%M %p")
