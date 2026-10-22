from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from actions.calendar_manager import manage_calendar
from core import calendar_store as cs
from core import calendar_reminders as cr
from core import heartbeat as hb


@pytest.fixture
def cal_file(tmp_path, monkeypatch):
    path = tmp_path / "calendar.json"
    monkeypatch.setattr(cs, "CALENDAR_FILE", path)
    yield path


@pytest.fixture
def hb_file(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat.json"
    monkeypatch.setattr(hb, "CONFIG_FILE", path)
    yield path


def test_schedule_event_advance_calls_reminder(cal_file):
    future = datetime.now() + timedelta(hours=2)
    date_str = future.strftime("%Y-%m-%d")
    time_str = future.strftime("%H:%M")
    calls = []

    def fake_reminder(params, **kwargs):
        calls.append(params["message"])
        return "ok"

    with patch("core.calendar_reminders.reminder", side_effect=fake_reminder):
        lines = cr.schedule_event_reminders(date_str, time_str, "Team sync", [15])
    assert any("In 15 minutes" in m for m in calls)
    assert any("Now:" in m for m in calls)
    assert len(lines) == 2


def test_add_schedules_advance(cal_file):
    future = datetime.now() + timedelta(days=1)
    with patch(
        "actions.calendar_manager.cr.schedule_event_reminders",
        return_value=["a", "b"],
    ) as sched:
        out = manage_calendar(
            {
                "action": "add",
                "date": future.strftime("%Y-%m-%d"),
                "time": "14:00",
                "description": "Demo",
            }
        )
    assert "Event added" in out
    assert "2 scheduled" in out
    sched.assert_called_once()


def test_effective_interval_urgent(hb_file, cal_file):
    hb.save_config(hb.load_config())
    near = datetime.now() + timedelta(minutes=10)
    cs.save(
        {
            "version": 2,
            "events_by_date": {
                near.strftime("%Y-%m-%d"): [
                    {
                        "id": "1",
                        "time": near.strftime("%H:%M"),
                        "description": "Soon",
                    }
                ]
            },
            "daily_routines": [],
            "settings": {},
        }
    )
    cfg = hb.load_config()
    assert hb.effective_interval_minutes(cfg) == cfg["interval_urgent_minutes"]


def test_briefing(cal_file):
    out = manage_calendar({"action": "briefing"})
    assert "Today" in out
