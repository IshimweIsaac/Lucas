from __future__ import annotations

import json
from datetime import datetime, timedelta
import pytest

from actions.heartbeat import heartbeat_control
from core import heartbeat as hb


@pytest.fixture
def hb_file(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat.json"
    monkeypatch.setattr(hb, "CONFIG_FILE", path)
    yield path


@pytest.fixture
def cal_file(tmp_path, monkeypatch):
    from core import calendar_store as cs

    path = tmp_path / "calendar.json"
    monkeypatch.setattr(cs, "CALENDAR_FILE", path)
    yield path


def test_should_run_when_never_ran(hb_file):
    hb.save_config({"enabled": True, "interval_minutes": 30, "last_run_iso": None})
    assert hb.should_run() is True


def test_should_not_run_when_recent(hb_file, monkeypatch):
    monkeypatch.setattr(hb.calendar_store, "minutes_until_next", lambda *args, **kwargs: None)
    last = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    hb.save_config({"enabled": True, "interval_minutes": 30, "last_run_iso": last})
    assert hb.should_run() is False


def test_build_wakeup_includes_routines(hb_file, monkeypatch):
    monkeypatch.setattr(
        hb.calendar_store,
        "load",
        lambda: {
            "version": 2,
            "events_by_date": {},
            "daily_routines": [
                {
                    "id": "x",
                    "time": "06:00",
                    "description": "Stretch",
                    "days": [hb.calendar_store.today_weekday()],
                    "enabled": True,
                }
            ],
        },
    )
    prompt = hb.build_wakeup_prompt({"checks": ["daily_routines"]})
    assert prompt is not None
    assert "Stretch" in prompt


def test_heartbeat_status(hb_file):
    out = heartbeat_control({"action": "status"})
    assert "Heartbeat is" in out


def test_queue_wakeup_writes_trigger(tmp_path, hb_file, monkeypatch):
    monkeypatch.setattr(hb.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        hb,
        "build_wakeup_prompt",
        lambda cfg=None: "[LUCAS HEARTBEAT] test",
    )
    hb.queue_wakeup()
    files = list((tmp_path / ".lucas" / "triggers").glob("trigger_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert "HEARTBEAT" in data["message"]
