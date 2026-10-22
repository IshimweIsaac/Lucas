"""Calendar: dated events, daily routines, briefings, and OS reminders."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from core import calendar_ics
from core import calendar_reminders as cr
from core import calendar_store as cs
from core import daily_schedule as ds
from memory.config_manager import get_base_dir

from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "calendar_manager",
    "description": (
        "Calendar and daily schedule: events, daily routines, advance warnings, "
        "briefing, import legacy reminders. Actions: add, list, delete, today, "
        "briefing, add_daily, list_daily, delete_daily, sync_daily, "
        "import_reminders, sync_ics."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "add | list | delete | today | briefing | "
                    "add_daily | list_daily | delete_daily | sync_daily | "
                    "import_reminders | sync_ics | dedupe_daily"
                ),
            },
            "ics_url": {
                "type": "STRING",
                "description": "Public ICS URL (sync_ics); else memory/calendar_sync.json",
            },
            "date": {"type": "STRING", "description": "Date YYYY-MM-DD for events"},
            "time": {"type": "STRING", "description": "Time HH:MM or 7:20 AM"},
            "description": {"type": "STRING", "description": "Event or routine text"},
            "event_id": {"type": "STRING", "description": "ID for delete"},
            "routine_id": {"type": "STRING", "description": "ID for daily routine delete"},
            "days": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Weekdays: mon,tue,... or all",
            },
            "enabled": {"type": "BOOLEAN", "description": "Enable daily routine"},
            "advance_minutes": {
                "type": "INTEGER",
                "description": "Minutes before event to warn (default 15; add uses 15+ at-event)",
            },
        },
        "required": ["action"],
    },
}


def _register_daily_os(routine: dict, cal: dict) -> str:
    hour, minute = cs.parse_time_hhmm(routine["time"])
    days = routine.get("days") or list(cs._WEEKDAYS)
    desc = routine.get("description", "Daily reminder")
    parts = [ds.schedule_daily(routine["id"], hour, minute, desc, days)]
    for mins in cr.get_daily_advance_minutes(cal):
        ah, am = cs.subtract_minutes(hour, minute, mins)
        parts.append(
            ds.schedule_daily(
                f"{routine['id']}_adv{mins}",
                ah,
                am,
                f"In {mins} minutes: {desc}",
                days,
            )
        )
    return " ".join(parts)


def _legacy_reminders_path() -> Path:
    return get_base_dir() / "Lucas notes" / "reminders.json"


def manage_calendar(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    data = cs.load()

    if action == "add":
        date_str = parameters.get("date", "").strip()
        time_str = parameters.get("time", "").strip()
        desc = parameters.get("description", "").strip()
        if not date_str or not time_str or not desc:
            return "Need date (YYYY-MM-DD), time, and description."
        try:
            hour, minute = cs.parse_time_hhmm(time_str)
            time_norm = f"{hour:02d}:{minute:02d}"
        except ValueError as e:
            return str(e)
        advances = cr.get_advance_minutes(data)
        if "advance_minutes" in parameters and parameters["advance_minutes"] is not None:
            advances = [max(1, int(parameters["advance_minutes"]))]

        event_id = str(uuid.uuid4())[:8]
        by_date = data.setdefault("events_by_date", {})
        by_date.setdefault(date_str, []).append(
            {"id": event_id, "time": time_norm, "description": desc}
        )
        by_date[date_str] = sorted(by_date[date_str], key=lambda x: x["time"])
        cs.save(data)

        scheduled = cr.schedule_event_reminders(
            date_str, time_norm, desc, advance_minutes=advances
        )
        if player:
            player.write_log(f"[Calendar] 📅 {desc} on {date_str} at {time_norm}")
        sched_note = f" Reminders: {len(scheduled)} scheduled (incl. {advances} min before)."
        return (
            f"Event added (id {event_id}) on {date_str} at {time_norm}: {desc}.{sched_note}"
        )

    if action == "list":
        date_str = parameters.get("date", "").strip()
        by_date = data.get("events_by_date", {})
        if date_str:
            events = by_date.get(date_str, [])
            if not events:
                return f"No events on {date_str}."
            lines = [f"Events for {date_str}:"]
            for e in events:
                lines.append(f"- [{e['time']}] {e['description']} (id {e['id']})")
            return "\n".join(lines)
        today = datetime.now().strftime("%Y-%m-%d")
        future = sorted(d for d in by_date if d >= today)
        if not future:
            return "No upcoming dated events."
        lines = ["Upcoming events:"]
        for d in future[:14]:
            lines.append(f"\n{d}:")
            for e in by_date[d]:
                lines.append(f"  - [{e['time']}] {e['description']} (id {e['id']})")
        return "\n".join(lines)

    if action == "delete":
        event_id = parameters.get("event_id", "").strip()
        if not event_id:
            return "Provide event_id to delete."
        by_date = data.get("events_by_date", {})
        for date_str, events in list(by_date.items()):
            kept = [e for e in events if e["id"] != event_id]
            if len(kept) < len(events):
                if kept:
                    by_date[date_str] = kept
                else:
                    del by_date[date_str]
                cs.save(data)
                if player:
                    player.write_log(f"[Calendar] 🗑️ deleted {event_id}")
                return f"Deleted event {event_id}."
        return f"No event with id {event_id}."

    if action == "today":
        ev = cs.events_today(data)
        routines = cs.routines_for_today(data)
        lines = [f"Today ({datetime.now().strftime('%A, %Y-%m-%d')}):"]
        if routines:
            lines.append("\nDaily schedule:")
            for r in routines:
                lines.append(f"  - [{r['time']}] {r['description']}")
        else:
            lines.append("\nNo daily routines today.")
        if ev:
            lines.append("\nCalendar events:")
            for e in ev:
                lines.append(f"  - [{e['time']}] {e['description']}")
        else:
            lines.append("\nNo extra events today.")
        lines.append("\n" + cs.format_next_up(data))
        return "\n".join(lines)

    if action == "briefing":
        lines = [
            f"Good { 'morning' if datetime.now().hour < 12 else 'afternoon' if datetime.now().hour < 17 else 'evening' }, sir.",
            "",
            manage_calendar({"action": "today"}, player=player),
        ]
        adv = cr.get_advance_minutes(data)
        lines.append(
            f"\nAdvance warnings are set to {adv} minutes before meetings/events."
        )
        return "\n".join(lines)

    if action == "add_daily":
        time_str = parameters.get("time", "").strip()
        desc = parameters.get("description", "").strip()
        if not time_str or not desc:
            return "Need time and description for a daily routine."
        try:
            hour, minute = cs.parse_time_hhmm(time_str)
            time_norm = f"{hour:02d}:{minute:02d}"
        except ValueError as e:
            return str(e)
        days = cs.normalize_days(parameters.get("days"))
        rid = cs.new_routine_id()
        routine = {
            "id": rid,
            "time": time_norm,
            "description": desc,
            "days": days,
            "enabled": parameters.get("enabled", True),
        }
        data.setdefault("daily_routines", []).append(routine)
        cs.save(data)
        os_msg = ""
        if routine["enabled"]:
            os_msg = " " + _register_daily_os(routine, data)
        if player:
            player.write_log(f"[Calendar] 🔁 Daily {time_norm} — {desc}")
        adv = cr.get_daily_advance_minutes(data)
        return (
            f"Daily routine added (id {rid}) at {time_norm}: {desc}. "
            f"OS reminders at routine time and {adv} min before.{os_msg}"
        )

    if action == "list_daily":
        routines = data.get("daily_routines", [])
        if not routines:
            return "No daily routines configured."
        adv = cr.get_daily_advance_minutes(data)
        lines = [f"Daily routines (advance warning: {adv} min):"]
        for r in routines:
            days = ",".join(r.get("days") or [])
            state = "on" if r.get("enabled", True) else "off"
            lines.append(
                f"- [{r['time']}] {r['description']} "
                f"(id {r['id']}, days: {days or 'all'}, {state})"
            )
        return "\n".join(lines)

    if action == "delete_daily":
        rid = parameters.get("routine_id", "").strip()
        if not rid:
            return "Provide routine_id."
        routines = data.get("daily_routines", [])
        kept = [r for r in routines if r["id"] != rid]
        if len(kept) == len(routines):
            return f"No daily routine with id {rid}."
        data["daily_routines"] = kept
        cs.save(data)
        ds.cancel_routine_jobs(rid, cr.get_daily_advance_minutes(data))
        if player:
            player.write_log(f"[Calendar] 🗑️ daily routine {rid}")
        return f"Deleted daily routine {rid} and cancelled OS schedules."

    if action == "sync_daily":
        results = []
        adv = cr.get_daily_advance_minutes(data)
        for r in data.get("daily_routines", []):
            if not r.get("enabled", True):
                ds.cancel_routine_jobs(r["id"], adv)
                results.append(f"{r['id']}: skipped (disabled)")
                continue
            ds.cancel_routine_jobs(r["id"], adv)
            msg = _register_daily_os(r, data)
            results.append(f"{r['id']}: {msg}")
        if not results:
            return "No daily routines to sync."
        return "Synced daily reminders:\n" + "\n".join(results)

    if action == "import_reminders":
        path = _legacy_reminders_path()
        if not path.exists():
            return f"No legacy file at {path}."
        try:
            legacy = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"Could not read reminders file: {e}"
        entries = legacy.get("daily_reminders") or []
        if not entries:
            return "Legacy file has no daily_reminders entries."
        imported = 0
        for entry in entries:
            t = (entry.get("time") or "").strip()
            desc = (entry.get("description") or "").strip()
            if not t or not desc:
                continue
            if "-" in t and "AM" in t.upper():
                t = t.split("-")[0].strip()
            manage_calendar(
                {"action": "add_daily", "time": t, "description": desc},
                player=player,
            )
            imported += 1
        return f"Imported {imported} daily routine(s) from legacy reminders.json."

    if action == "dedupe_daily":
        routines = data.get("daily_routines", [])
        seen: set[tuple[str, str]] = set()
        unique: list[dict] = []
        removed = 0
        for r in routines:
            key = (r.get("time", ""), (r.get("description") or "").strip().lower())
            if key in seen:
                removed += 1
                ds.cancel_routine_jobs(r["id"], cr.get_daily_advance_minutes(data))
                continue
            seen.add(key)
            unique.append(r)
        data["daily_routines"] = unique
        cs.save(data)
        return f"Removed {removed} duplicate daily routine(s). {len(unique)} remain."

    if action == "sync_ics":
        url = parameters.get("ics_url", "").strip()
        try:
            if url:
                _, msg = calendar_ics.sync_from_url(url)
            else:
                _, msg = calendar_ics.sync_configured()
            return msg
        except Exception as e:
            return f"ICS sync failed: {e}"

    return (
        f"Unknown action: {action}. Use add, list, delete, today, briefing, "
        "add_daily, list_daily, delete_daily, sync_daily, import_reminders, sync_ics."
    )
