"""Lucas heartbeat — periodic wake-up checks while Live session is running."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from core import calendar_store
from core import pc_control
from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

CONFIG_FILE = get_base_dir() / "memory" / "heartbeat.json"

_DEFAULT = {
    "enabled": True,
    "interval_minutes": 30,
    "interval_urgent_minutes": 5,
    "interval_near_minutes": 10,
    "near_event_threshold_minutes": 60,
    "urgent_event_threshold_minutes": 15,
    "checks": ["calendar_today", "daily_routines", "upcoming_events", "system_health"],
    "last_run_iso": None,
    "speak_summary": True,
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("heartbeat: failed to load config, using defaults")
        return dict(_DEFAULT)
    merged = dict(_DEFAULT)
    for key in _DEFAULT:
        if key in data:
            merged[key] = data[key]
    if "custom_prompt" in data:
        merged["custom_prompt"] = data["custom_prompt"]
    return merged


def save_config(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark_run(cfg: dict | None = None) -> None:
    data = cfg if cfg is not None else load_config()
    data["last_run_iso"] = datetime.now().isoformat(timespec="seconds")
    save_config(data)


def effective_interval_minutes(cfg: dict | None = None) -> int:
    """Shorter interval when a calendar item is coming soon."""
    data = cfg if cfg is not None else load_config()
    base = max(5, int(data.get("interval_minutes", 30)))
    urgent = max(3, int(data.get("interval_urgent_minutes", 5)))
    near = max(5, int(data.get("interval_near_minutes", 10)))
    urgent_thr = int(data.get("urgent_event_threshold_minutes", 15))
    near_thr = int(data.get("near_event_threshold_minutes", 60))

    mins = calendar_store.minutes_until_next()
    if mins is None:
        return base
    if mins <= urgent_thr:
        return urgent
    if mins <= near_thr:
        return near
    return base


def poll_interval_seconds(cfg: dict | None = None) -> int:
    """How long main.py should sleep between heartbeat checks."""
    return max(30, min(120, effective_interval_minutes(cfg) * 60 // 2))


def should_run(cfg: dict | None = None) -> bool:
    data = cfg if cfg is not None else load_config()
    if not data.get("enabled", True):
        return False
    last = data.get("last_run_iso")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        logger.warning("heartbeat: invalid last_run_iso %r, running", last)
        return True
    interval = effective_interval_minutes(data)
    return datetime.now() >= last_dt + timedelta(minutes=interval)


def _upcoming_events_summary(cal: dict, days: int = 3) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    by_date = cal.get("events_by_date", {})
    keys = sorted(d for d in by_date if d >= today)[:days]
    if not keys:
        return "No upcoming dated events."
    lines = []
    for d in keys:
        lines.append(f"{d}:")
        for ev in by_date[d]:
            lines.append(f"  - [{ev.get('time')}] {ev.get('description')} (id {ev.get('id')})")
    return "\n".join(lines)


def build_wakeup_prompt(cfg: dict | None = None) -> str | None:
    """Build a system prompt for Lucas to 'wake up' and review state."""
    data = cfg if cfg is not None else load_config()
    checks = data.get("checks") or _DEFAULT["checks"]
    cal = calendar_store.load()
    sections: list[str] = []

    next_up = calendar_store.format_next_up(cal, within_minutes=120)
    mins = calendar_store.minutes_until_next(cal)
    if mins is not None and mins <= int(data.get("near_event_threshold_minutes", 60)):
        sections.append(next_up)

    if "calendar_today" in checks or "daily_routines" in checks:
        ev = calendar_store.events_today(cal)
        routines = calendar_store.routines_for_today(cal)
        if "calendar_today" in checks:
            if ev:
                sections.append(
                    "Today's calendar events:\n"
                    + "\n".join(f"- [{e['time']}] {e['description']}" for e in ev)
                )
            else:
                sections.append("No one-off calendar events today.")
        if "daily_routines" in checks:
            if routines:
                sections.append(
                    "Today's daily schedule:\n"
                    + "\n".join(
                        f"- [{r['time']}] {r['description']}" for r in routines
                    )
                )
            else:
                sections.append("No daily routines configured for today.")

    if "upcoming_events" in checks:
        sections.append("Upcoming events:\n" + _upcoming_events_summary(cal))

    if "system_health" in checks:
        b = pc_control.battery_status()
        if b:
            ch = "charging" if b.get("charging") else "on battery"
            sections.append(f"System: battery {b['percent']}% ({ch}).")
            if pc_control.battery_low(20):
                sections.append(
                    "URGENT: Battery is low. Remind the user to plug in the charger now."
                )
        vol = pc_control.volume_get()
        if vol is not None:
            sections.append(f"System: volume {vol}%.")

    custom = (data.get("custom_prompt") or "").strip()
    if custom:
        sections.append(f"User heartbeat note: {custom}")

    if not sections:
        return None

    body = "\n\n".join(sections)
    speak = data.get("speak_summary", True)
    urgent_thr = int(data.get("urgent_event_threshold_minutes", 15))
    if mins is not None and mins <= urgent_thr:
        instruction = (
            "Something is starting very soon. Speak clearly: what it is, "
            "how many minutes remain, and one short prep tip if useful."
        )
    elif speak:
        instruction = (
            "Briefly tell the user only if something needs attention "
            "(event in the next hour, missed routine, or urgent custom note). "
            "Otherwise stay silent or give a one-line all-clear."
        )
    else:
        instruction = "Review internally; only speak if action is required."

    interval = effective_interval_minutes(data)
    return (
        "[LUCAS HEARTBEAT — scheduled check]\n"
        f"(Heartbeat interval right now: {interval} min)\n"
        f"{body}\n\n"
        f"{instruction}"
    )


def queue_wakeup(cfg: dict | None = None) -> str | None:
    """Write a trigger file so the Live session processes a heartbeat immediately."""
    prompt = build_wakeup_prompt(cfg)
    if not prompt:
        return None
    trigger_dir = Path.home() / ".lucas" / "triggers"
    trigger_dir.mkdir(parents=True, exist_ok=True)
    path = trigger_dir / f"trigger_{time.time_ns()}_{os.getpid()}.json"
    path.write_text(
        json.dumps({"message": prompt, "source": "heartbeat"}),
        encoding="utf-8",
    )
    data = cfg if cfg is not None else load_config()
    mark_run(data)
    return prompt
