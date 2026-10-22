"""Calendar persistence: dated events + daily routines."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from memory.config_manager import get_base_dir

CALENDAR_FILE = get_base_dir() / "memory" / "calendar.json"

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DATE_KEY_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _empty() -> dict:
    return {
        "version": 2,
        "events_by_date": {},
        "daily_routines": [],
        "settings": {
            "advance_warning_minutes": [15],
            "daily_advance_minutes": [15],
        },
    }


def load() -> dict:
    if not CALENDAR_FILE.exists():
        return _empty()
    try:
        raw = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty()
    if not isinstance(raw, dict):
        return _empty()
    if raw.get("version") == 2:
        raw.setdefault("events_by_date", {})
        raw.setdefault("daily_routines", [])
        raw.setdefault("settings", _empty()["settings"])
        return raw
    # Migrate legacy flat date → events map
    events = {k: v for k, v in raw.items() if _DATE_KEY_RE.match(str(k))}
    return {"version": 2, "events_by_date": events, "daily_routines": []}


def save(data: dict) -> None:
    CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "events_by_date": data.get("events_by_date", {}),
        "daily_routines": data.get("daily_routines", []),
        "settings": data.get("settings", _empty()["settings"]),
    }
    CALENDAR_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_time_hhmm(time_str: str) -> tuple[int, int]:
    """Accept HH:MM (24h) or h:MM AM/PM."""
    t = time_str.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            dt = datetime.strptime(t, fmt)
            return dt.hour, dt.minute
        except ValueError:
            continue
    raise ValueError(f"Could not parse time: {time_str}")


def normalize_days(days: list[str] | None) -> list[str]:
    if not days:
        return list(_WEEKDAYS)
    out: list[str] = []
    for d in days:
        key = d.strip().lower()[:3]
        if key in ("all", "every", "daily"):
            return list(_WEEKDAYS)
        if key in _WEEKDAYS:
            out.append(key)
    return out or list(_WEEKDAYS)


def today_weekday() -> str:
    return _WEEKDAYS[datetime.now().weekday()]


def routines_for_today(data: dict) -> list[dict]:
    dow = today_weekday()
    result = []
    for r in data.get("daily_routines", []):
        if not r.get("enabled", True):
            continue
        days = r.get("days") or list(_WEEKDAYS)
        if dow in days or "all" in days:
            result.append(r)
    return sorted(result, key=lambda x: x.get("time", ""))


def events_today(data: dict) -> list[dict]:
    key = datetime.now().strftime("%Y-%m-%d")
    return sorted(data.get("events_by_date", {}).get(key, []), key=lambda x: x.get("time", ""))


def new_routine_id() -> str:
    return str(uuid.uuid4())[:8]


def subtract_minutes(hour: int, minute: int, delta: int) -> tuple[int, int]:
    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    adj = base - timedelta(minutes=delta)
    return adj.hour, adj.minute


@dataclass
class UpcomingItem:
    when: datetime
    description: str
    kind: str  # event | routine
    minutes_until: float


def _parse_event_dt(date_str: str, time_str: str) -> datetime:
    hour, minute = parse_time_hhmm(time_str)
    return datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def iter_today_upcoming(data: dict | None = None) -> list[UpcomingItem]:
    """All dated events and daily routines still ahead today."""
    cal = data if data is not None else load()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    items: list[UpcomingItem] = []

    for ev in cal.get("events_by_date", {}).get(today, []):
        try:
            when = _parse_event_dt(today, ev["time"])
        except ValueError:
            continue
        if when >= now:
            delta = (when - now).total_seconds() / 60
            items.append(
                UpcomingItem(when, ev.get("description", "Event"), "event", delta)
            )

    for r in routines_for_today(cal):
        try:
            hour, minute = parse_time_hhmm(r["time"])
            when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            continue
        if when >= now:
            delta = (when - now).total_seconds() / 60
            items.append(
                UpcomingItem(
                    when, r.get("description", "Routine"), "routine", delta
                )
            )

    return sorted(items, key=lambda x: x.when)


def minutes_until_next(data: dict | None = None) -> float | None:
    upcoming = iter_today_upcoming(data)
    if not upcoming:
        return None
    return upcoming[0].minutes_until


def format_next_up(data: dict | None = None, within_minutes: int = 120) -> str:
    items = [
        i for i in iter_today_upcoming(data) if i.minutes_until <= within_minutes
    ]
    if not items:
        return "Nothing scheduled in the next 2 hours."
    lines = ["Coming up soon:"]
    for i in items[:6]:
        mins = int(i.minutes_until)
        label = "now" if mins <= 1 else f"in {mins} min"
        lines.append(f"- {label}: [{i.when.strftime('%H:%M')}] {i.description}")
    return "\n".join(lines)
