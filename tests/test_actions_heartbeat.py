"""Tests for actions/heartbeat.py — heartbeat control tool.

NOTE: This tests actions/heartbeat.py, NOT core/heartbeat.py (which has its own
test file at tests/test_heartbeat.py)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.heartbeat import TOOL_SCHEMA, heartbeat_control


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "heartbeat"
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_action_status():
    """action=status returns heartbeat status string."""
    fake_cfg = {
        "enabled": True,
        "interval_minutes": 30,
        "checks": ["calendar_today", "daily_routines"],
        "last_run_iso": "2026-06-25T10:00:00",
    }
    with patch("actions.heartbeat.hb.load_config", return_value=fake_cfg):
        result = heartbeat_control(parameters={"action": "status"})

    assert "Heartbeat is on" in result
    assert "30 min" in result
    assert "calendar_today" in result
    assert "2026-06-25" in result


def test_action_status_disabled():
    """action=status reflects disabled state."""
    fake_cfg = {
        "enabled": False,
        "interval_minutes": 30,
        "checks": [],
        "last_run_iso": None,
    }
    with patch("actions.heartbeat.hb.load_config", return_value=fake_cfg):
        result = heartbeat_control(parameters={"action": "status"})

    assert "Heartbeat is off" in result
    assert "none" in result or "never" in result


def test_action_configure_enabled():
    """action=configure updates enabled field."""
    cfg = {"enabled": True, "interval_minutes": 30, "checks": [], "last_run_iso": None}
    with (
        patch("actions.heartbeat.hb.load_config", return_value=dict(cfg)),
        patch("actions.heartbeat.hb.save_config") as mock_save,
    ):
        result = heartbeat_control(
            parameters={"action": "configure", "enabled": False}
        )

    assert "off" in result
    # save_config was called with enabled=False
    saved = mock_save.call_args[0][0]
    assert saved["enabled"] is False


def test_action_configure_interval():
    """action=configure clamps interval to minimum 5."""
    cfg = {"enabled": True, "interval_minutes": 30, "checks": [], "last_run_iso": None}
    with (
        patch("actions.heartbeat.hb.load_config", return_value=dict(cfg)),
        patch("actions.heartbeat.hb.save_config") as mock_save,
    ):
        heartbeat_control(
            parameters={"action": "configure", "interval_minutes": 2}
        )

    saved = mock_save.call_args[0][0]
    assert saved["interval_minutes"] == 5


def test_action_configure_checks():
    """action=configure only allows valid check values."""
    cfg = {"enabled": True, "interval_minutes": 30, "checks": [], "last_run_iso": None}
    with (
        patch("actions.heartbeat.hb.load_config", return_value=dict(cfg)),
        patch("actions.heartbeat.hb.save_config") as mock_save,
    ):
        heartbeat_control(
            parameters={
                "action": "configure",
                "checks": ["calendar_today", "invalid_check"],
            }
        )

    saved = mock_save.call_args[0][0]
    assert "calendar_today" in saved["checks"]
    assert "invalid_check" not in saved["checks"]


def test_action_configure_custom_prompt():
    """action=configure saves custom_prompt."""
    cfg = {"enabled": True, "interval_minutes": 30, "checks": [], "last_run_iso": None}
    with (
        patch("actions.heartbeat.hb.load_config", return_value=dict(cfg)),
        patch("actions.heartbeat.hb.save_config") as mock_save,
    ):
        heartbeat_control(
            parameters={"action": "configure", "custom_prompt": "Check emails"}
        )

    saved = mock_save.call_args[0][0]
    assert saved["custom_prompt"] == "Check emails"


def test_action_configure_with_player():
    """action=configure writes log via player when provided."""
    cfg = {"enabled": True, "interval_minutes": 30, "checks": [], "last_run_iso": None}
    mock_player = MagicMock()
    with (
        patch("actions.heartbeat.hb.load_config", return_value=dict(cfg)),
        patch("actions.heartbeat.hb.save_config"),
    ):
        heartbeat_control(
            parameters={"action": "configure", "enabled": True},
            player=mock_player,
        )

    mock_player.write_log.assert_called_once()


def test_action_run_now():
    """action=run_now queues a heartbeat check."""
    cfg = {
        "enabled": True,
        "interval_minutes": 30,
        "checks": ["calendar_today"],
        "last_run_iso": None,
    }
    with (
        patch("actions.heartbeat.hb.load_config", return_value=cfg),
        patch(
            "actions.heartbeat.hb.queue_wakeup",
            return_value="[LUCAS HEARTBEAT] Check calendar",
        ),
    ):
        result = heartbeat_control(parameters={"action": "run_now"})

    assert "queued" in result
    assert "calendar" in result


def test_action_run_now_nothing():
    """action=run_now returns message when there's nothing to check."""
    cfg = {
        "enabled": True,
        "interval_minutes": 30,
        "checks": ["calendar_today"],
        "last_run_iso": None,
    }
    with (
        patch("actions.heartbeat.hb.load_config", return_value=cfg),
        patch("actions.heartbeat.hb.queue_wakeup", return_value=""),
    ):
        result = heartbeat_control(parameters={"action": "run_now"})

    assert "nothing to check" in result


def test_unknown_action():
    """An unrecognized action returns an error."""
    result = heartbeat_control(parameters={"action": "restart"})
    assert "Unknown action" in result


def test_parameters_default_to_empty():
    """Missing or empty action is handled gracefully."""
    result = heartbeat_control(parameters={"action": ""})
    assert "Unknown action" in result
