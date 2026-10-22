from __future__ import annotations

import json

from actions import lucas_service
from core import alert_delivery as ad
from core import calendar_ics
from core import systemd_service as svc


def test_write_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "TRIGGER_DIR", tmp_path / "triggers")
    p = ad.write_trigger("Hello", source="test")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["message"] == "Hello"


def test_parse_ics_event():
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20270115T140000Z
SUMMARY:Team standup
END:VEVENT
END:VCALENDAR"""
    events = calendar_ics.parse_ics_events(ics, horizon_days=3650)
    assert len(events) == 1
    assert events[0]["description"] == "Team standup"
    assert events[0]["time"] == "14:00"


def test_systemd_unit_contains_main():
    from memory.config_manager import get_base_dir

    text = svc._unit_content(get_base_dir(), "/usr/bin/python3")
    assert "main.py" in text


def test_lucas_service_enable_wake(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "WAKE_FLAG", tmp_path / "wake")
    out = lucas_service.lucas_service({"action": "enable_wake"})
    assert "enabled" in out.lower()
    assert (tmp_path / "wake").exists()


def test_deliver_alert_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "TRIGGER_DIR", tmp_path / "triggers")
    monkeypatch.setattr(ad, "desktop_notify", lambda *a, **k: True)
    monkeypatch.setattr(ad, "play_alert_sound", lambda: True)
    monkeypatch.setattr(ad, "wake_lucas_if_needed", lambda: "skip")
    r = ad.deliver_alert("Test", try_wake=False)
    assert r.get("notify") is True
    assert (tmp_path / "triggers").exists()
