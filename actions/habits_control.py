"""Lucas Habits control — voice action for habits and goals tracking."""

from __future__ import annotations

from core import habits_core
from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "habits_control",
    "description": (
        "Track habits and goals. Create/list/delete habits, log today's habit, "
        "view habit logs, create/list/update/delete goals with progress tracking, "
        "and view overall stats."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "create_habit | list_habits | delete_habit | log_habit | "
                    "habit_logs | create_goal | list_goals | "
                    "update_goal_progress | delete_goal | habits_stats | help"
                ),
            },
            "name": {
                "type": "STRING",
                "description": "Name of the habit or goal to create",
            },
            "habit_id": {
                "type": "STRING",
                "description": "Habit ID (e.g. habit-1)",
            },
            "goal_id": {
                "type": "STRING",
                "description": "Goal ID (e.g. goal-1)",
            },
            "frequency": {
                "type": "STRING",
                "description": "daily | weekly | monthly (default: daily)",
            },
            "description": {
                "type": "STRING",
                "description": "Optional description for habit or goal",
            },
            "target_date": {
                "type": "STRING",
                "description": "Target date in YYYY-MM-DD format (goals)",
            },
            "progress": {
                "type": "INTEGER",
                "description": "Progress percentage 0-100 (update_goal_progress)",
            },
            "days": {
                "type": "INTEGER",
                "description": "Number of days to show in habit_logs",
            },
        },
        "required": ["action"],
    },
}


def habits_control(parameters: dict, player=None) -> str:
    """Dispatch habits and goals actions based on the action parameter."""
    action = (parameters.get("action") or "").lower().strip()
    name = (parameters.get("name") or "").strip()
    habit_id = (parameters.get("habit_id") or "").strip()
    goal_id = (parameters.get("goal_id") or "").strip()
    frequency = (parameters.get("frequency") or "daily").strip()
    description = (parameters.get("description") or "").strip()
    target_date = (parameters.get("target_date") or "").strip()
    progress_param = parameters.get("progress")
    days = parameters.get("days")

    # ── Habit actions ──

    if action == "create_habit":
        if not name:
            return "A name is required to create a habit."
        result = habits_core.create_habit(name, frequency, description)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    if action == "list_habits":
        return habits_core.list_habits()

    if action == "delete_habit":
        if not habit_id:
            return "A habit_id is required to delete a habit."
        result = habits_core.delete_habit(habit_id)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    if action == "log_habit":
        if not habit_id:
            return "A habit_id is required to log a habit."
        result = habits_core.log_habit(habit_id)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    if action == "habit_logs":
        if not habit_id:
            return "A habit_id is required to view habit logs."
        days_val = int(days) if days is not None else 7
        return habits_core.habit_logs(habit_id, days_val)

    # ── Goal actions ──

    if action == "create_goal":
        if not name:
            return "A name is required to create a goal."
        result = habits_core.create_goal(name, target_date, description)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    if action == "list_goals":
        return habits_core.list_goals()

    if action == "update_goal_progress":
        if not goal_id:
            return "A goal_id is required to update progress."
        if progress_param is None:
            return "A progress value (0-100) is required."
        try:
            progress_val = int(progress_param)
        except (TypeError, ValueError):
            return "Progress must be an integer between 0 and 100."
        result = habits_core.update_goal_progress(goal_id, progress_val)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    if action == "delete_goal":
        if not goal_id:
            return "A goal_id is required to delete a goal."
        result = habits_core.delete_goal(goal_id)
        if player:
            player.write_log(f"[Habits] {result}")
        return result

    # ── Stats / Help ──

    if action == "habits_stats":
        return habits_core.habits_stats()

    if action == "help":
        return (
            "habits_control actions:\n"
            "  create_habit name=... [frequency=daily] [description=...]\n"
            "  list_habits\n"
            "  delete_habit habit_id=...\n"
            "  log_habit habit_id=...\n"
            "  habit_logs habit_id=... [days=7]\n"
            "  create_goal name=... [target_date=YYYY-MM-DD] [description=...]\n"
            "  list_goals\n"
            "  update_goal_progress goal_id=... progress=0-100\n"
            "  delete_goal goal_id=...\n"
            "  habits_stats\n"
            "  help"
        )

    return f"Unknown action: {action}. Use action=help to see available actions."
