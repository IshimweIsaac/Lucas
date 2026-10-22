"""Schedule one-off and advance reminders for calendar events."""

from __future__ import annotations

from datetime import datetime, timedelta

from actions.reminder import reminder
from core import calendar_store as cs


def get_advance_minutes(cal: dict | None = None) -> list[int]:
    data = cal if cal is not None else cs.load()
    settings = data.get("settings") or {}
    raw = settings.get("advance_warning_minutes", [15])
    if isinstance(raw, int):
        raw = [raw]
    out = sorted({int(m) for m in raw if int(m) > 0}, reverse=True)
    return out or [15]


def get_daily_advance_minutes(cal: dict | None = None) -> list[int]:
    data = cal if cal is not None else cs.load()
    settings = data.get("settings") or {}
    raw = settings.get("daily_advance_minutes")
    if raw is None:
        return get_advance_minutes(data)
    if isinstance(raw, int):
        raw = [raw]
    return sorted({int(m) for m in raw if int(m) > 0}, reverse=True) or [15]


def schedule_event_reminders(
    date_str: str,
    time_norm: str,
    description: str,
    advance_minutes: list[int] | None = None,
) -> list[str]:
    """Schedule at-event and advance OS reminders. Returns status lines."""
    cal = cs.load()
    advances = advance_minutes if advance_minutes is not None else get_advance_minutes(cal)
    event_dt = datetime.strptime(f"{date_str} {time_norm}", "%Y-%m-%d %H:%M")
    now = datetime.now()
    results: list[str] = []

    for mins in advances:
        adv_dt = event_dt - timedelta(minutes=mins)
        if adv_dt <= now:
            continue
        msg = f"In {mins} minutes: {description}"
        out = reminder(
            {
                "date": adv_dt.strftime("%Y-%m-%d"),
                "time": adv_dt.strftime("%H:%M"),
                "message": msg,
            }
        )
        results.append(f"T-{mins}min: {out}")

    if event_dt > now:
        out = reminder(
            {
                "date": date_str,
                "time": time_norm,
                "message": f"Now: {description}",
            }
        )
        results.append(f"At event: {out}")
    return results
