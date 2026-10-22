"""Lucas Habits — local JSON-backed habit tracker."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_HABITS_DIR = Path(__file__).resolve().parent.parent / "memory" / "habits"
_HABITS_FILE = _HABITS_DIR / "habits.json"
_LOGS_FILE = _HABITS_DIR / "logs.json"
_GOALS_FILE = _HABITS_DIR / "goals.json"


def _ensure_dirs() -> None:
    _HABITS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> list:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []
    return []


def _save_json(path: Path, data: list) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── HABITS ──


def create_habit(name: str, frequency: str = "daily", description: str = "") -> str:
    """Create a new habit and return a result message."""
    habits = _load_json(_HABITS_FILE)
    hid = f"habit-{len(habits) + 1}"
    habits.append(
        {
            "id": hid,
            "name": name,
            "frequency": frequency,
            "description": description,
            "streak": 0,
            "best_streak": 0,
            "created": datetime.now().isoformat(),
        }
    )
    _save_json(_HABITS_FILE, habits)
    return f"Habit created: {name} ({hid}) — {frequency}"


def list_habits() -> str:
    """Return a formatted list of all habits."""
    habits = _load_json(_HABITS_FILE)
    if not habits:
        return "No habits. Create one with create_habit."
    lines = [f"Habits ({len(habits)}):"]
    for h in habits:
        streak = h.get("streak", 0)
        lines.append(f"  {h['name']} ({h['frequency']}) — {streak} day streak")
    return "\n".join(lines)


def delete_habit(habit_id: str) -> str:
    """Delete a habit by its ID."""
    habits = _load_json(_HABITS_FILE)
    new_habits = [h for h in habits if h["id"] != habit_id]
    if len(new_habits) == len(habits):
        return f"Habit not found: {habit_id}"
    _save_json(_HABITS_FILE, new_habits)
    return f"Habit deleted: {habit_id}"


# ── LOGGING ──


def log_habit(habit_id: str) -> str:
    """Log a habit for today and update the streak."""
    habits = _load_json(_HABITS_FILE)
    habit = None
    for h in habits:
        if h["id"] == habit_id:
            habit = h
            break
    if not habit:
        return f"Habit not found: {habit_id}"

    logs = _load_json(_LOGS_FILE)
    today_str = date.today().isoformat()

    # Check if already logged today
    for log in logs:
        if log["habit_id"] == habit_id and log["date"] == today_str:
            return f"Habit '{habit['name']}' already logged today!"

    logs.append(
        {
            "habit_id": habit_id,
            "date": today_str,
            "time": datetime.now().isoformat(),
        }
    )
    _save_json(_LOGS_FILE, logs)

    # Calculate streak
    streak = _calculate_streak(habit_id)
    habit["streak"] = streak
    if streak > habit.get("best_streak", 0):
        habit["best_streak"] = streak
    _save_json(_HABITS_FILE, habits)

    msg = f"Habit logged: {habit['name']} — {streak} day streak"
    if streak >= 3:
        msg += " 🔥"
    return msg


def _calculate_streak(habit_id: str) -> int:
    """Calculate the current consecutive-day streak for a habit."""
    logs = _load_json(_LOGS_FILE)
    habit_logs = sorted(
        [log for log in logs if log["habit_id"] == habit_id],
        key=lambda x: x["date"],
        reverse=True,
    )
    if not habit_logs:
        return 0

    streak = 0
    check_date = date.today()
    for log in habit_logs:
        log_date = date.fromisoformat(log["date"])
        if log_date == check_date or log_date == check_date - timedelta(days=1):
            streak += 1
            check_date = log_date
        elif log_date < check_date - timedelta(days=1):
            break
    return streak


def habit_logs(habit_id: str, days: int = 7) -> str:
    """Return recent log entries for a habit."""
    logs = _load_json(_LOGS_FILE)
    habit_entries = [entry for entry in logs if entry["habit_id"] == habit_id]
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    recent = [entry for entry in habit_entries if entry["date"] >= cutoff]

    habits = _load_json(_HABITS_FILE)
    habit_name = next((h["name"] for h in habits if h["id"] == habit_id), habit_id)

    if not recent:
        return f"No logs for '{habit_name}' in the last {days} days."
    return f"Logs for '{habit_name}' ({len(recent)} entries):\n" + "\n".join(
        f"  {entry['date']}" for entry in reversed(recent)
    )


# ── GOALS ──


def create_goal(name: str, target_date: str = "", description: str = "") -> str:
    """Create a new goal and return a result message."""
    goals = _load_json(_GOALS_FILE)
    gid = f"goal-{len(goals) + 1}"
    goals.append(
        {
            "id": gid,
            "name": name,
            "description": description,
            "target_date": target_date,
            "status": "active",
            "progress": 0,
            "created": datetime.now().isoformat(),
        }
    )
    _save_json(_GOALS_FILE, goals)
    return f"Goal created: {name} ({gid})"


def list_goals() -> str:
    """Return a formatted list of all goals."""
    goals = _load_json(_GOALS_FILE)
    if not goals:
        return "No goals."
    lines = ["Goals:"]
    for g in goals:
        progress = g.get("progress", 0)
        bar = "▓" * (progress // 10) + "░" * (10 - progress // 10)
        lines.append(f"  {bar} {g['name']} ({g.get('status', 'active')}) — {progress}%")
    return "\n".join(lines)


def update_goal_progress(goal_id: str, progress: int) -> str:
    """Update the progress percentage for a goal."""
    goals = _load_json(_GOALS_FILE)
    for g in goals:
        if g["id"] == goal_id:
            g["progress"] = min(100, max(0, progress))
            if g["progress"] >= 100:
                g["status"] = "completed"
            _save_json(_GOALS_FILE, goals)
            return f"Goal '{g['name']}' progress: {g['progress']}%"
    return f"Goal not found: {goal_id}"


def delete_goal(goal_id: str) -> str:
    """Delete a goal by its ID."""
    goals = _load_json(_GOALS_FILE)
    new_goals = [g for g in goals if g["id"] != goal_id]
    if len(new_goals) == len(goals):
        return f"Goal not found: {goal_id}"
    _save_json(_GOALS_FILE, new_goals)
    return f"Goal deleted: {goal_id}"


def habits_stats() -> str:
    """Return a brief statistics string for habits and goals."""
    habits = _load_json(_HABITS_FILE)
    goals = _load_json(_GOALS_FILE)
    active_goals = sum(1 for g in goals if g.get("status") == "active")
    done_goals = sum(1 for g in goals if g.get("status") == "completed")
    return (
        f"{len(habits)} habits tracked, "
        f"{len(goals)} goals ({active_goals} active, {done_goals} completed)"
    )
