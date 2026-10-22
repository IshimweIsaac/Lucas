from __future__ import annotations

from unittest.mock import patch

from actions.pc_controller import pc_controller
from core import system_clock as clock
from memory import session_brief as sb


def test_format_time_contains_clock_fields():
    out = clock.format_time()
    assert "Current time:" in out
    assert "24h" in out


def test_pc_controller_time_action():
    out = pc_controller({"action": "time"})
    assert out.startswith("Current time:")


def test_pc_controller_date_action():
    out = pc_controller({"action": "date"})
    assert out.startswith("Today is")


def test_session_brief_skips_stale_time_bullets(tmp_path, monkeypatch):
    path = tmp_path / "session_brief.json"
    monkeypatch.setattr(sb, "BRIEF_PATH", path)
    sb.clear_brief()
    sb.add_bullet("Lucas: The current time is 08:34 AM.")
    sb.add_bullet("User: open chrome")
    out = sb.format_for_prompt()
    assert "08:34" not in out
    assert "open chrome" in out


def test_status_includes_datetime():
    from core import pc_control as pc

    with patch.object(pc, "battery_status", return_value=None):
        with patch.object(pc, "volume_get", return_value=None):
            with patch.object(pc, "brightness_get", return_value=None):
                with patch.object(pc, "list_windows", return_value=[]):
                    out = pc.system_status_report()
    assert "Current time:" in out
