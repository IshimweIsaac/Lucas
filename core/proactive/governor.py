"""Anti-nag governor — pacing, quiet hours, DND, and daily budget counters.

Decides whether the proactive engine may work at all (`can_work`) and whether
an engagement may be SPOKEN vs silently queued (`allowed_to_speak`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.proactive import engagement_store

_IDLE_SPEAK_THRESHOLD_SEC = 600


def _parse_hhmm(value: str) -> int | None:
    try:
        hours, minutes = (value or "").strip().split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(cfg: dict | None = None, now: datetime | None = None) -> bool:
    """True when *now* falls inside the configured quiet window (wraps midnight)."""
    data = cfg or {}
    start = _parse_hhmm(data.get("quiet_start", "22:00"))
    end = _parse_hhmm(data.get("quiet_end", "06:00"))
    if start is None or end is None or start == end:
        return False
    current = now or datetime.now()
    minute = current.hour * 60 + current.minute
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def dnd_active(cfg: dict | None = None, now: datetime | None = None) -> bool:
    """True when DND is enabled or the DND window has not expired."""
    data = cfg or {}
    if data.get("dnd_enabled"):
        return True
    until = data.get("dnd_until_iso")
    if not until:
        return False
    try:
        until_dt = datetime.fromisoformat(str(until))
    except (TypeError, ValueError):
        return False
    return (now or datetime.now()) < until_dt


def can_work(
    cfg: dict | None = None,
    counters: dict | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Whether the engine should run at all this tick.

    Returns (ok, reason) with reason one of: "ok", "disabled", "quiet hours",
    "dnd", "pacing", "budget llm", "budget reads".
    """
    data = cfg or {}
    if not data.get("enabled", True):
        return False, "disabled"
    if in_quiet_hours(data, now=now):
        return False, "quiet hours"
    if dnd_active(data, now=now):
        return False, "dnd"

    counters = counters or engagement_store.get_daily_counters()
    budget = data.get("budget", {})
    if int(counters.get("llm", 0)) >= int(budget.get("max_llm_ticks_per_day", 6)):
        return False, "budget llm"
    if int(counters.get("reads", 0)) >= int(
        budget.get("max_project_reads_per_day", 6)
    ):
        return False, "budget reads"

    last = engagement_store.last_engagement()
    if last and last.get("at"):
        min_between = int(
            data.get("engagement", {}).get("min_minutes_between", 60)
        )
        try:
            last_dt = datetime.fromisoformat(str(last["at"]))
            since = (now or datetime.now()) - last_dt
            if since < timedelta(minutes=min_between):
                return False, "pacing"
        except (TypeError, ValueError):
            pass
    return True, "ok"


def allowed_to_speak(
    cfg: dict | None = None,
    counters: dict | None = None,
    muted: bool = False,
    idle_seconds: int = 0,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Whether an engagement may be spoken now vs queued silently.

    Returns (ok, reason) with reason one of: "ok", "quiet hours", "dnd",
    "budget speech", "muted", "idle".
    """
    data = cfg or {}
    if in_quiet_hours(data, now=now):
        return False, "quiet hours"
    if dnd_active(data, now=now):
        return False, "dnd"

    counters = counters or engagement_store.get_daily_counters()
    max_speech = int(data.get("engagement", {}).get("max_speech_per_day", 3))
    if int(counters.get("speech", 0)) >= max_speech:
        return False, "budget speech"

    respect_mute = bool(data.get("engagement", {}).get("respect_ui_mute", True))
    if respect_mute and muted:
        return False, "muted"
    if int(idle_seconds or 0) > _IDLE_SPEAK_THRESHOLD_SEC:
        return False, "idle"
    return True, "ok"


def budget_left(cfg: dict | None, counters: dict | None, kind: str) -> int:
    """Remaining budget for *kind* ("llm", "web", "reads", "speech")."""
    data = cfg or {}
    budget = data.get("budget", {})
    if kind == "speech":
        cap = int(data.get("engagement", {}).get("max_speech_per_day", 3))
    else:
        key = {
            "llm": "max_llm_ticks_per_day",
            "web": "max_web_searches_per_day",
            "reads": "max_project_reads_per_day",
        }.get(kind)
        cap = int(budget.get(key, 0)) if key else 0
    counters = counters or engagement_store.get_daily_counters()
    return max(0, cap - int(counters.get(kind, 0)))


def tick_usage(kind: str, n: int = 1) -> None:
    """Thin wrapper to consume budget for *kind* (llm/web/reads/speech)."""
    engagement_store.bump_counter(kind, n=n)