"""Predictive automation for Lucas — tracks activity patterns and makes context-aware suggestions."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.context_engine import get_context
from core.logger import get_logger

logger = get_logger(__name__)

_TRACKING_FILE = Path.home() / ".lucas" / "activity_tracking.json"
_MAX_ENTRIES = 1000

_activity_log: list[dict[str, Any]] = []
_loaded = False


def _load_tracking() -> None:
    """Load activity tracking data from file."""
    global _activity_log, _loaded
    if _loaded:
        return
    try:
        if _TRACKING_FILE.exists() and _TRACKING_FILE.stat().st_size > 0:
            data = _TRACKING_FILE.read_text(encoding="utf-8")
            if data.strip():
                _activity_log = json.loads(data)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load activity tracking: %s", exc)
        _activity_log = []
    _loaded = True


def _save_tracking() -> None:
    """Save activity tracking data to file."""
    try:
        _TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TRACKING_FILE.write_text(json.dumps(_activity_log, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not save activity tracking: %s", exc)


def log_activity(activity: str, details: str = "") -> None:
    """Log what the user is doing.

    Called by context engine periodically. Keeps max 1000 entries, trimming oldest.
    """
    _load_tracking()
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "activity": activity,
        "details": details,
    }
    _activity_log.append(entry)
    # Trim oldest entries
    if len(_activity_log) > _MAX_ENTRIES:
        _activity_log[:] = _activity_log[-_MAX_ENTRIES:]
    _save_tracking()


def _build_hourly_patterns() -> dict[str, dict[str, int]]:
    """Analyze activity log for patterns grouped by hour and activity.

    Returns dict: {hour_label: {activity: count}}
    """
    _load_tracking()
    patterns: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in _activity_log:
        try:
            ts = datetime.datetime.fromisoformat(entry["timestamp"])
            hour_label = ts.strftime("%H:00")
            activity = entry.get("activity", "unknown")
            patterns[hour_label][activity] += 1
        except (ValueError, KeyError):
            continue
    return dict(patterns)


def _build_day_hour_patterns() -> dict[str, dict[str, dict[str, int]]]:
    """Analyze activity log for patterns grouped by day + hour + activity.

    Returns dict: {day_name: {hour_label: {activity: count}}}
    """
    _load_tracking()
    patterns: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for entry in _activity_log:
        try:
            ts = datetime.datetime.fromisoformat(entry["timestamp"])
            day_name = ts.strftime("%A")
            hour_label = ts.strftime("%H:00")
            activity = entry.get("activity", "unknown")
            patterns[day_name][hour_label][activity] += 1
        except (ValueError, KeyError):
            continue
    return dict(patterns)


def get_patterns() -> str:
    """Analyze activity log for patterns.

    Returns a human-readable summary of detected patterns.
    """
    _load_tracking()
    if not _activity_log:
        return "No activity data yet. Start using Lucas and I'll learn your patterns."

    day_hour = _build_day_hour_patterns()
    now = datetime.datetime.now()
    current_day = now.strftime("%A")
    current_hour = now.strftime("%H:00")

    insights: list[str] = []

    # Check current day + hour for patterns
    if current_day in day_hour and current_hour in day_hour[current_day]:
        top_activities = sorted(
            day_hour[current_day][current_hour].items(),
            key=lambda x: -x[1],
        )
        if top_activities:
            top_act, count = top_activities[0]
            if count >= 2:
                insights.append(
                    f"You often {top_act} around this time on {current_day}s "
                    f"({count} times)."
                )

    # Check general hourly patterns
    hourly = _build_hourly_patterns()
    for hour_label in sorted(hourly.keys()):
        h = int(hour_label.split(":")[0])
        activities = hourly[hour_label]
        top = max(activities, key=activities.get)
        count = activities[top]
        if count >= 3:
            ampm = "am" if h < 12 else "pm"
            hour_display = f"{h % 12 or 12}{ampm}"
            insights.append(
                f"You typically {top} around {hour_display} ({count} times)."
            )

    if not insights:
        return "Not enough data for patterns yet. Continue using your PC normally."

    return "Pattern analysis:\n" + "\n".join(f"- {i}" for i in insights[:5])


def suggest_next_action() -> str:
    """Based on patterns and current context, suggest what the user might want."""
    ctx = get_context()
    process = (ctx.get("active_process") or "").lower()
    cpu = ctx.get("cpu_usage", 0)
    mem = ctx.get("memory_usage", 0)
    bat = ctx.get("battery_percent")
    idle = ctx.get("user_idle_seconds", 0)
    hour = datetime.datetime.now().hour
    day = datetime.datetime.now().strftime("%A")

    suggestions: list[str] = []

    # Battery low
    if bat is not None and bat <= 20:
        suggestions.append(f"Battery is low ({bat}%). Plug in your charger.")
    elif bat is not None and bat <= 30 and idle > 60:
        suggestions.append(
            f"Battery at {bat}%. Consider plugging in if you will be here a while."
        )

    # Check if user has been working long
    if process and not idle > 120:
        suggestions.append("You seem focused. I'm here if you need anything.")

    # Time-based suggestions
    if hour >= 22:
        suggestions.append(
            "It's getting late. Would you like to set a reminder to wind down?"
        )
    elif hour >= 17 and hour < 19:
        if day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
            suggestions.append(
                "End of workday — would you like a summary of what you did today?"
            )

    # Memory pressure
    if mem > 85:
        suggestions.append(
            f"Memory is high ({mem}%). Close some applications to keep things snappy?"
        )

    # High CPU
    if cpu > 80:
        suggestions.append(f"CPU is high ({cpu}%). Check if something is misbehaving?")

    # Pattern-based suggestion
    day_hour = _build_day_hour_patterns()
    current_day = day
    current_hour = f"{hour:02d}:00"
    if current_day in day_hour and current_hour in day_hour[current_day]:
        top_activities = sorted(
            day_hour[current_day][current_hour].items(),
            key=lambda x: -x[1],
        )
        if top_activities:
            top_act, _ = top_activities[0]
            # Don't suggest what user is already doing
            if top_act.lower() != process.lower():
                suggestions.append(
                    f"You usually {top_act} around this time. Would you like to?"
                )

    if not suggestions:
        suggestions.append(
            "Everything looks normal. Just let me know if you need anything."
        )

    return "\n".join(suggestions)
