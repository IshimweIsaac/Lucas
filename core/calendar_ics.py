"""Import events from a public ICS / Google Calendar URL (read-only)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from urllib.request import urlopen

from core import calendar_store as cs
from memory.config_manager import get_base_dir

SYNC_CONFIG = get_base_dir() / "memory" / "calendar_sync.json"


def _load_sync_config() -> dict:
    if not SYNC_CONFIG.exists():
        return {}
    try:
        return json.loads(SYNC_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _unfold_ics(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return "\n".join(out)


def _parse_ics_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1]
        for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    if "T" in value:
        try:
            return datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        except ValueError:
            pass
    try:
        return datetime.strptime(value[:8], "%Y%m%d")
    except ValueError:
        return None


def parse_ics_events(ics_text: str, *, horizon_days: int = 60) -> list[dict]:
    """Return list of {date, time, description} for upcoming VEVENTs."""
    text = _unfold_ics(ics_text)
    blocks = re.split(r"BEGIN:VEVENT", text)[1:]
    now = datetime.now()
    horizon = now + timedelta(days=horizon_days)
    events: list[dict] = []

    for block in blocks:
        chunk = block.split("END:VEVENT", 1)[0]
        summary_m = re.search(r"^SUMMARY(?:;[^:]*)?:(.+)$", chunk, re.M)
        dtstart_m = re.search(r"^DTSTART(?:;[^:]*)?:(.+)$", chunk, re.M)
        if not dtstart_m:
            continue
        start = _parse_ics_datetime(dtstart_m.group(1))
        if not start or start < now - timedelta(days=1) or start > horizon:
            continue
        desc = (summary_m.group(1).strip() if summary_m else "Calendar event")
        desc = desc.replace("\\n", " ").replace("\\,", ",")[:200]
        events.append(
            {
                "date": start.strftime("%Y-%m-%d"),
                "time": start.strftime("%H:%M"),
                "description": desc,
            }
        )
    return events


def fetch_ics(url: str, timeout: int = 30) -> str:
    with urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def sync_from_url(url: str, *, horizon_days: int = 60) -> tuple[int, str]:
    ics = fetch_ics(url)
    parsed = parse_ics_events(ics, horizon_days=horizon_days)
    if not parsed:
        return 0, "No upcoming events found in feed."

    data = cs.load()
    by_date = data.setdefault("events_by_date", {})
    added = 0
    for ev in parsed:
        d, t, desc = ev["date"], ev["time"], ev["description"]
        by_date.setdefault(d, [])
        if any(e.get("description") == desc and e.get("time") == t for e in by_date[d]):
            continue
        by_date[d].append(
            {"id": str(uuid.uuid4())[:8], "time": t, "description": f"[ICS] {desc}"}
        )
        added += 1
        by_date[d] = sorted(by_date[d], key=lambda x: x["time"])
    cs.save(data)
    return added, f"Imported {added} event(s) from calendar feed (next {horizon_days} days)."


def sync_configured() -> tuple[int, str]:
    cfg = _load_sync_config()
    url = (cfg.get("ics_url") or cfg.get("url") or "").strip()
    if not url:
        return 0, "No ics_url in memory/calendar_sync.json"
    days = int(cfg.get("horizon_days", 60))
    return sync_from_url(url, horizon_days=days)
