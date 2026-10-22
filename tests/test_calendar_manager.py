from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from actions.calendar_manager import manage_calendar
from core import calendar_store as cs


@pytest.fixture
def cal_file(tmp_path, monkeypatch):
    path = tmp_path / "calendar.json"
    monkeypatch.setattr(cs, "CALENDAR_FILE", path)
    yield path


def test_migrate_legacy_format(cal_file):
    cal_file.write_text(
        json.dumps({"2026-06-01": [{"id": "a1", "time": "09:00", "description": "Meet"}]}),
        encoding="utf-8",
    )
    data = cs.load()
    assert data["version"] == 2
    assert "2026-06-01" in data["events_by_date"]


def test_add_daily_and_list(cal_file):
    with patch("actions.calendar_manager._register_daily_os", return_value="scheduled"):
        out = manage_calendar(
            {
                "action": "add_daily",
                "time": "07:00",
                "description": "Wake up",
                "days": ["mon", "tue"],
            }
        )
    assert "Daily routine added" in out
    data = cs.load()
    assert len(data["daily_routines"]) == 1
    assert data["daily_routines"][0]["days"] == ["mon", "tue"]

    listed = manage_calendar({"action": "list_daily"})
    assert "Wake up" in listed


def test_today_includes_routine(cal_file, monkeypatch):
    dow = cs.today_weekday()
    cs.save(
        {
            "version": 2,
            "events_by_date": {},
            "daily_routines": [
                {
                    "id": "r1",
                    "time": "08:00",
                    "description": "Coffee",
                    "days": [dow],
                    "enabled": True,
                }
            ],
        }
    )
    out = manage_calendar({"action": "today"})
    assert "Coffee" in out


def test_parse_time_ampm():
    h, m = cs.parse_time_hhmm("7:20 AM")
    assert (h, m) == (7, 20)
