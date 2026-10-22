"""Tests for actions/lucas_service.py — background service management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.lucas_service import TOOL_SCHEMA, lucas_service


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "lucas_service"
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_action_status(tmp_path, monkeypatch):
    """action=status returns presence + systemd status."""
    monkeypatch.setattr(
        "actions.lucas_service.presence_status.format_report",
        lambda: "=== Lucas presence ===",
    )
    monkeypatch.setattr(
        "actions.lucas_service.svc.status",
        lambda: "Systemd: active",
    )
    result = lucas_service(parameters={"action": "status"})
    assert "Lucas presence" in result
    assert "Systemd: active" in result


def test_action_install(tmp_path, monkeypatch):
    """action=install delegates to systemd_service.install."""
    monkeypatch.setattr(
        "actions.lucas_service.svc.install",
        lambda: "Systemd unit installed.",
    )
    result = lucas_service(parameters={"action": "install"})
    assert "installed" in result


def test_action_install_with_player(monkeypatch):
    """action=install writes log via player when provided."""
    mock_player = MagicMock()
    monkeypatch.setattr(
        "actions.lucas_service.svc.install",
        lambda: "Systemd unit installed.",
    )
    lucas_service(parameters={"action": "install"}, player=mock_player)
    mock_player.write_log.assert_called_once()


def test_action_uninstall(monkeypatch):
    """action=uninstall delegates to systemd_service.uninstall."""
    monkeypatch.setattr(
        "actions.lucas_service.svc.uninstall",
        lambda: "Systemd unit removed.",
    )
    result = lucas_service(parameters={"action": "uninstall"})
    assert "removed" in result


def test_action_enable_wake(tmp_path, monkeypatch):
    """action=enable_wake creates the wake flag file."""
    wake_file = tmp_path / "wake_on_alert"
    monkeypatch.setattr("actions.lucas_service.ad.WAKE_FLAG", wake_file)
    result = lucas_service(parameters={"action": "enable_wake"})
    assert "enabled" in result
    assert wake_file.exists()


def test_action_disable_wake(tmp_path, monkeypatch):
    """action=disable_wake removes the wake flag file."""
    wake_file = tmp_path / "wake_on_alert"
    wake_file.touch()
    monkeypatch.setattr("actions.lucas_service.ad.WAKE_FLAG", wake_file)
    result = lucas_service(parameters={"action": "disable_wake"})
    assert "disabled" in result
    assert not wake_file.exists()


def test_action_snooze(monkeypatch):
    """action=snooze delegates to snooze_mod.schedule_snooze."""
    monkeypatch.setattr(
        "actions.lucas_service.snooze_mod.schedule_snooze",
        lambda mins, msg: f"Snoozed for {mins} min: {msg}",
    )
    result = lucas_service(
        parameters={"action": "snooze", "minutes": 15, "message": "Meeting"}
    )
    assert "15" in result
    assert "Meeting" in result


def test_action_snooze_defaults(monkeypatch):
    """action=snooze uses default values when parameters are missing."""
    monkeypatch.setattr(
        "actions.lucas_service.snooze_mod.schedule_snooze",
        lambda mins, msg: f"Snoozed for {mins} min: {msg}",
    )
    result = lucas_service(parameters={"action": "snooze"})
    assert "10" in result  # default minutes
    assert "Reminder" in result  # default message


def test_action_setup(monkeypatch):
    """action=setup runs the full setup routine."""
    wake_file = MagicMock()
    monkeypatch.setattr("actions.lucas_service.ad.WAKE_FLAG", wake_file)
    monkeypatch.setattr(
        "actions.lucas_service.presence_status.format_report",
        lambda: "=== Lucas presence ===",
    )
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(
        "actions.lucas_service.svc.install",
        lambda: "Systemd unit installed.",
    )
    mock_calendar = MagicMock(return_value="Calendar synced.")
    with patch("actions.calendar_manager.manage_calendar", mock_calendar):
        result = lucas_service(parameters={"action": "setup"})

    assert "Lucas presence" in result
    assert "Systemd unit installed" in result
    assert mock_calendar.call_count == 2


def test_unknown_action():
    """An unrecognized action returns an error."""
    result = lucas_service(parameters={"action": "fly"})
    assert "Unknown action" in result


def test_parameters_default_to_empty():
    """Missing parameters dict is handled gracefully."""
    result = lucas_service(parameters={"action": ""})
    assert "Unknown action" in result
