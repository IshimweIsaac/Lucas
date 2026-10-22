"""Tests for habits_core data layer and habits_control action module."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from actions.habits_control import habits_control
from core import habits_core as hc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def habits_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Replace all three JSON file paths with tmp_path versions."""
    habits_file = tmp_path / "habits.json"
    logs_file = tmp_path / "logs.json"
    goals_file = tmp_path / "goals.json"
    monkeypatch.setattr(hc, "_HABITS_FILE", habits_file)
    monkeypatch.setattr(hc, "_LOGS_FILE", logs_file)
    monkeypatch.setattr(hc, "_GOALS_FILE", goals_file)
    return tmp_path


@pytest.fixture
def seeded_habits(habits_env: Path) -> str:
    """Create one habit and return its ID."""
    return habits_control(
        {
            "action": "create_habit",
            "name": "Morning run",
            "frequency": "daily",
        }
    )


@pytest.fixture
def seeded_goals(habits_env: Path) -> str:
    """Create one goal and return its ID."""
    return habits_control(
        {
            "action": "create_goal",
            "name": "Read 12 books",
            "target_date": "2026-12-31",
        }
    )


# ---------------------------------------------------------------------------
# Helper to extract ID from result string
# ---------------------------------------------------------------------------

_HABIT_ID_RE = r"habit-\d+"
_GOAL_ID_RE = r"goal-\d+"


def _parse_habit_id(result: str) -> str:
    """Extract the habit ID from a creation result string."""
    for word in result.split():
        if word.startswith("(habit-"):
            return word.strip("()")
    raise ValueError(f"Cannot parse habit ID from: {result}")


def _parse_goal_id(result: str) -> str:
    """Extract the goal ID from a creation result string."""
    for word in result.split():
        if word.startswith("(goal-"):
            return word.strip("()")
    raise ValueError(f"Cannot parse goal ID from: {result}")


# ===================================================================
# HABIT TESTS
# ===================================================================


class TestCreateHabit:
    def test_create_habit_basic(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "create_habit",
                "name": "Meditate",
            }
        )
        assert "Habit created" in result
        assert "Meditate" in result

    def test_create_habit_with_description(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "create_habit",
                "name": "Journal",
                "description": "Write 3 things I'm grateful for",
            }
        )
        assert "Habit created" in result

    def test_create_habit_weekly(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "create_habit",
                "name": "Grocery shop",
                "frequency": "weekly",
            }
        )
        assert "weekly" in result

    def test_create_habit_empty_name(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "create_habit",
                "name": "",
            }
        )
        assert "name is required" in result

    def test_create_habit_core_function(self, habits_env: Path) -> None:
        result = hc.create_habit("Drink water")
        assert "Habit created" in result
        assert "Drink water" in result

    def test_create_multiple_habits_sequential_ids(self, habits_env: Path) -> None:
        r1 = _parse_habit_id(hc.create_habit("Habit A"))
        r2 = _parse_habit_id(hc.create_habit("Habit B"))
        assert r1 == "habit-1"
        assert r2 == "habit-2"


class TestListHabits:
    def test_list_habits_empty(self, habits_env: Path) -> None:
        result = hc.list_habits()
        assert "No habits" in result

    def test_list_habits_with_data(self, habits_env: Path) -> None:
        hc.create_habit("Exercise")
        hc.create_habit("Read")
        result = hc.list_habits()
        assert "Exercise" in result
        assert "Read" in result
        assert "2" in result or "2)" in result or "Habits (2)" in result

    def test_list_habits_shows_streak(self, habits_env: Path) -> None:
        hc.create_habit("Code daily")
        result = hc.list_habits()
        assert "0 day streak" in result


class TestDeleteHabit:
    def test_delete_habit(self, habits_env: Path) -> None:
        r = hc.create_habit("To delete")
        hid = _parse_habit_id(r)
        result = hc.delete_habit(hid)
        assert "deleted" in result
        assert hc.list_habits() == "No habits. Create one with create_habit."

    def test_delete_habit_not_found(self, habits_env: Path) -> None:
        result = hc.delete_habit("habit-999")
        assert "not found" in result

    def test_delete_habit_action(self, habits_env: Path) -> None:
        hc.create_habit("Temp")
        result = habits_control({"action": "delete_habit", "habit_id": "habit-1"})
        assert "deleted" in result


class TestLogHabit:
    def test_log_habit(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Yoga"))
        result = hc.log_habit(rid)
        assert "logged" in result
        assert "1 day streak" in result

    def test_log_habit_not_found(self, habits_env: Path) -> None:
        result = hc.log_habit("habit-999")
        assert "not found" in result

    def test_log_habit_already_logged(self, habits_env: Path, monkeypatch) -> None:
        rid = _parse_habit_id(hc.create_habit("Duplicates"))
        hc.log_habit(rid)
        result = hc.log_habit(rid)
        assert "already logged" in result

    def test_log_via_action(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Push-ups"))
        result = habits_control({"action": "log_habit", "habit_id": rid})
        assert "logged" in result

    def test_log_without_id(self, habits_env: Path) -> None:
        result = habits_control({"action": "log_habit", "habit_id": ""})
        assert "A habit_id is required" in result


class TestStreak:
    def test_streak_two_consecutive_days(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Consistent"))
        # Write two logs manually on consecutive days
        logs = [
            {
                "habit_id": rid,
                "date": (date.today() - timedelta(days=1)).isoformat(),
                "time": "2026-01-01T00:00:00",
            },
            {
                "habit_id": rid,
                "date": date.today().isoformat(),
                "time": "2026-01-02T00:00:00",
            },
        ]
        hc._save_json(hc._LOGS_FILE, logs)
        streak = hc._calculate_streak(rid)
        assert streak == 2

    def test_streak_breaks(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Broken"))
        logs = [
            {
                "habit_id": rid,
                "date": (date.today() - timedelta(days=3)).isoformat(),
                "time": "2026-01-01T00:00:00",
            },
            {
                "habit_id": rid,
                "date": date.today().isoformat(),
                "time": "2026-01-04T00:00:00",
            },
        ]
        hc._save_json(hc._LOGS_FILE, logs)
        streak = hc._calculate_streak(rid)
        # Today minus 3 days gap => only today counts (no consecutive)
        assert streak == 1

    def test_streak_no_logs(self, habits_env: Path) -> None:
        assert hc._calculate_streak("nonexistent") == 0

    def test_log_updates_best_streak(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Best streak test"))
        # Seed yesterday's log only; log_habit will add today's entry
        logs = [
            {
                "habit_id": rid,
                "date": (date.today() - timedelta(days=1)).isoformat(),
                "time": "2026-01-01T00:00:00",
            },
        ]
        hc._save_json(hc._LOGS_FILE, logs)

        habits = hc._load_json(hc._HABITS_FILE)
        for h in habits:
            if h["id"] == rid:
                assert h["streak"] == 0  # not updated yet

        # log_habit should add today and calculate streak 2
        hc.log_habit(rid)
        habits = hc._load_json(hc._HABITS_FILE)
        for h in habits:
            if h["id"] == rid:
                assert h["streak"] == 2
                assert h["best_streak"] == 2


class TestHabitLogs:
    def test_habit_logs_empty(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Unlogged"))
        result = hc.habit_logs(rid)
        assert "No logs" in result

    def test_habit_logs_with_entry(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Logged habit"))
        hc.log_habit(rid)
        result = hc.habit_logs(rid)
        assert "1 entries" in result or "1" in result

    def test_habit_logs_nonexistent_habit(self, habits_env: Path) -> None:
        result = hc.habit_logs("habit-999")
        assert "No logs" in result


# ===================================================================
# GOAL TESTS
# ===================================================================


class TestCreateGoal:
    def test_create_goal(self, habits_env: Path) -> None:
        result = hc.create_goal("Learn Rust")
        assert "Goal created" in result

    def test_create_goal_with_date(self, habits_env: Path) -> None:
        result = hc.create_goal("Run marathon", target_date="2027-06-01")
        assert "Goal created" in result

    def test_create_goal_via_action(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "create_goal",
                "name": "Write a book",
            }
        )
        assert "Goal created" in result

    def test_create_goal_missing_name(self, habits_env: Path) -> None:
        result = habits_control({"action": "create_goal", "name": ""})
        assert "name is required" in result


class TestListGoals:
    def test_list_goals_empty(self, habits_env: Path) -> None:
        result = hc.list_goals()
        assert "No goals" in result or "Goals:" not in result

    def test_list_goals_with_data(self, habits_env: Path) -> None:
        hc.create_goal("Goal A")
        hc.create_goal("Goal B")
        result = hc.list_goals()
        assert "Goal A" in result
        assert "Goal B" in result


class TestUpdateGoalProgress:
    def test_update_progress(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Save money"))
        result = hc.update_goal_progress(rid, 50)
        assert "50%" in result

    def test_update_progress_completes_goal(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Finish project"))
        hc.update_goal_progress(rid, 100)
        goals = hc._load_json(hc._GOALS_FILE)
        for g in goals:
            if g["id"] == rid:
                assert g["status"] == "completed"

    def test_update_progress_clamps_high(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Overachiever"))
        result = hc.update_goal_progress(rid, 150)
        assert "100%" in result

    def test_update_progress_clamps_low(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Underachiever"))
        result = hc.update_goal_progress(rid, -10)
        assert "0%" in result

    def test_update_progress_not_found(self, habits_env: Path) -> None:
        result = hc.update_goal_progress("goal-999", 50)
        assert "not found" in result

    def test_update_goal_via_action(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Action test"))
        result = habits_control(
            {
                "action": "update_goal_progress",
                "goal_id": rid,
                "progress": 75,
            }
        )
        assert "75%" in result

    def test_update_goal_missing_progress(self, habits_env: Path) -> None:
        result = habits_control(
            {
                "action": "update_goal_progress",
                "goal_id": "goal-1",
            }
        )
        assert "progress value" in result


class TestDeleteGoal:
    def test_delete_goal(self, habits_env: Path) -> None:
        rid = _parse_goal_id(hc.create_goal("Delete me"))
        result = hc.delete_goal(rid)
        assert "deleted" in result

    def test_delete_goal_not_found(self, habits_env: Path) -> None:
        result = hc.delete_goal("goal-999")
        assert "not found" in result

    def test_delete_goal_via_action(self, habits_env: Path) -> None:
        hc.create_goal("Temp goal")
        result = habits_control({"action": "delete_goal", "goal_id": "goal-1"})
        assert "deleted" in result


# ===================================================================
# STATS / HELP
# ===================================================================


class TestStats:
    def test_habits_stats_empty(self, habits_env: Path) -> None:
        result = hc.habits_stats()
        assert "0 habits" in result
        assert "0 goals" in result

    def test_habits_stats_with_data(self, habits_env: Path) -> None:
        hc.create_habit("Exercise")
        hc.create_goal("Goal X")
        hc.create_goal("Goal Y")
        hc.update_goal_progress("goal-2", 100)
        result = hc.habits_stats()
        assert "1 habits" in result
        assert "2 goals" in result
        assert "1 active" in result
        assert "1 completed" in result


class TestHelp:
    def test_help_action(self, habits_env: Path) -> None:
        result = habits_control({"action": "help"})
        assert "create_habit" in result
        assert "list_goals" in result
        assert "log_habit" in result

    def test_unknown_action(self, habits_env: Path) -> None:
        result = habits_control({"action": "bogus"})
        assert "Unknown action" in result


# ===================================================================
# EDGE CASES
# ===================================================================


class TestEdgeCases:
    def test_data_persistence(self, habits_env: Path) -> None:
        """Verify data is actually written to disk."""
        hc.create_habit("Persistent habit")
        raw = json.loads(hc._HABITS_FILE.read_text(encoding="utf-8"))
        assert len(raw) == 1
        assert raw[0]["name"] == "Persistent habit"

    def test_goal_data_persistence(self, habits_env: Path) -> None:
        hc.create_goal("Persistent goal")
        raw = json.loads(hc._GOALS_FILE.read_text(encoding="utf-8"))
        assert len(raw) == 1
        assert raw[0]["name"] == "Persistent goal"

    def test_log_data_persistence(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Logged"))
        hc.log_habit(rid)
        raw = json.loads(hc._LOGS_FILE.read_text(encoding="utf-8"))
        assert len(raw) == 1
        assert raw[0]["habit_id"] == rid

    def test_habit_logs_respects_days_param(self, habits_env: Path) -> None:
        rid = _parse_habit_id(hc.create_habit("Old habit"))
        # Write a very old log entry
        old_date = (date.today() - timedelta(days=30)).isoformat()
        hc._save_json(
            hc._LOGS_FILE,
            [
                {"habit_id": rid, "date": old_date, "time": "2026-01-01T00:00:00"},
            ],
        )
        result = hc.habit_logs(rid, days=7)
        assert "No logs" in result

        result_wide = hc.habit_logs(rid, days=60)
        assert old_date in result_wide

    def test_multiple_habits_independent_streaks(self, habits_env: Path) -> None:
        h1 = _parse_habit_id(hc.create_habit("Habit A"))
        h2 = _parse_habit_id(hc.create_habit("Habit B"))
        hc.log_habit(h1)
        hc.log_habit(h2)
        habits = hc._load_json(hc._HABITS_FILE)
        for h in habits:
            assert h["streak"] == 1
