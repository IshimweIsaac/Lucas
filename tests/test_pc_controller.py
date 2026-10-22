"""Tests for actions/pc_controller.py — PC control tool.

NOTE: This tests actions/pc_controller.py, NOT core/pc_control.py (which has its own
test file at tests/test_pc_control.py)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.pc_controller import TOOL_SCHEMA, pc_controller
from core import pc_control as pc
from core import system_clock as clock


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "pc_controller"
    assert "action" in TOOL_SCHEMA["parameters"]["required"]
    assert TOOL_SCHEMA["parameters"]["properties"]["action"]["type"] == "STRING"


# ---------------------------------------------------------------------------
# Clock actions (time / date / datetime)
# ---------------------------------------------------------------------------


def test_action_time():
    """action=time delegates to clock.format_time."""
    with patch.object(clock, "format_time", return_value="Current time: 02:30 PM (14:30 24h)."):
        result = pc_controller({"action": "time"})

    assert "Current time" in result
    assert "02:30" in result


def test_action_time_alternate_names():
    """Alternate action names for time work correctly."""
    with patch.object(clock, "format_time", return_value="Current time: 10:00 AM."):
        for name in ("current_time", "what_time"):
            result = pc_controller({"action": name})
            assert "Current time" in result


def test_action_date():
    """action=date delegates to clock.format_date."""
    with patch.object(clock, "format_date", return_value="Today is Friday, June 26, 2026."):
        result = pc_controller({"action": "date"})

    assert "Today is" in result


def test_action_date_alternate_names():
    """Alternate action names for date work correctly."""
    with patch.object(clock, "format_date", return_value="Today is Friday."):
        for name in ("current_date", "what_date", "today"):
            result = pc_controller({"action": name})
            assert "Today is" in result


def test_action_datetime():
    """action=datetime delegates to clock.format_datetime."""
    with patch.object(clock, "format_datetime", return_value="Current time: ... Date: ..."):
        result = pc_controller({"action": "datetime"})

    assert "Current time" in result

    with patch.object(clock, "format_datetime", return_value="Current time: ... Date: ..."):
        result = pc_controller({"action": "now"})

    assert "Current time" in result


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_action_status():
    """action=status delegates to pc.system_status_report."""
    with patch.object(pc, "system_status_report", return_value="=== PC status ==="):
        result = pc_controller({"action": "status"})

    assert "PC status" in result


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


def test_action_volume_set():
    """action=volume_set delegates to pc.volume_set with the value."""
    with patch.object(pc, "volume_set", return_value="Volume set to 40%."):
        result = pc_controller({"action": "volume_set", "value": 40})

    assert "40" in result


def test_action_volume_set_alternate_name():
    """action=set_volume works the same as volume_set."""
    with patch.object(pc, "volume_set", return_value="Volume set to 50%."):
        result = pc_controller({"action": "set_volume", "value": 50})

    assert "50" in result


def test_action_volume_set_missing_value():
    """action=volume_set without a value returns an error."""
    result = pc_controller({"action": "volume_set"})
    assert "Provide value" in result


def test_action_volume_up():
    """action=volume_up increases volume by 10 via pc.volume_get / volume_set."""
    with (
        patch.object(pc, "volume_get", return_value=50),
        patch.object(pc, "volume_set", return_value="Volume set to 60%.") as mock_set,
    ):
        result = pc_controller({"action": "volume_up"})
        assert "60" in result or "Volume set" in result
        mock_set.assert_called_with(60)


def test_action_volume_up_no_current():
    """action=volume_up uses 50+10 when volume_get returns None."""
    with (
        patch.object(pc, "volume_get", return_value=None),
        patch.object(pc, "volume_set", return_value="Volume set to 60%.") as mock_set,
    ):
        result = pc_controller({"action": "volume_up"})
        assert "60" in result or "Volume set" in result
        mock_set.assert_called_with(60)


def test_action_volume_down():
    """action=volume_down decreases volume by 10."""
    with (
        patch.object(pc, "volume_get", return_value=50),
        patch.object(pc, "volume_set", return_value="Volume set to 40%.") as mock_set,
    ):
        result = pc_controller({"action": "volume_down"})
        assert "40" in result or "Volume set" in result
        mock_set.assert_called_with(40)


def test_action_mute():
    """action=mute delegates to pc.volume_mute_toggle."""
    with patch.object(pc, "volume_mute_toggle", return_value="Toggled mute."):
        result = pc_controller({"action": "mute"})

    assert "mute" in result


def test_action_mute_alternate_names():
    """Alternate action names for mute work correctly."""
    with patch.object(pc, "volume_mute_toggle", return_value="Toggled mute."):
        for name in ("toggle_mute", "unmute"):
            result = pc_controller({"action": name})
            assert "mute" in result


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------


def test_action_brightness_set():
    """action=brightness_set delegates to pc.brightness_set."""
    with patch.object(pc, "brightness_set", return_value="Brightness set to 70%."):
        result = pc_controller({"action": "brightness_set", "value": 70})

    assert "70" in result


def test_action_brightness_set_alternate_name():
    """action=set_brightness works the same as brightness_set."""
    with patch.object(pc, "brightness_set", return_value="Brightness set to 30%."):
        result = pc_controller({"action": "set_brightness", "value": 30})

    assert "30" in result


def test_action_brightness_set_missing_value():
    """action=brightness_set without a value returns an error."""
    result = pc_controller({"action": "brightness_set"})
    assert "Provide value" in result


def test_action_brightness_up():
    """action=brightness_up increases brightness by 10."""
    with (
        patch.object(pc, "brightness_get", return_value=50),
        patch.object(pc, "brightness_set", return_value="Brightness set to 60%.") as mock_set,
    ):
        result = pc_controller({"action": "brightness_up"})
        assert "60" in result or "Brightness set" in result
        mock_set.assert_called_with(60)


def test_action_brightness_up_no_current():
    """action=brightness_up uses 50+10 when brightness_get returns None."""
    with (
        patch.object(pc, "brightness_get", return_value=None),
        patch.object(pc, "brightness_set", return_value="Brightness set to 60%.") as mock_set,
    ):
        result = pc_controller({"action": "brightness_up"})
        assert "60" in result or "Brightness set" in result
        mock_set.assert_called_with(60)


def test_action_brightness_down():
    """action=brightness_down decreases brightness by 10."""
    with (
        patch.object(pc, "brightness_get", return_value=50),
        patch.object(pc, "brightness_set", return_value="Brightness set to 40%.") as mock_set,
    ):
        result = pc_controller({"action": "brightness_down"})
        assert "40" in result or "Brightness set" in result
        mock_set.assert_called_with(40)


# ---------------------------------------------------------------------------
# Focus / Close app
# ---------------------------------------------------------------------------


def test_action_focus_app_browser():
    """action=focus_app with 'chrome' calls pc.focus_browser."""
    with patch.object(pc, "focus_browser", return_value="Focused: Google Chrome"):
        result = pc_controller({"action": "focus_app", "app": "chrome"})

    assert "Focused" in result


def test_action_focus_app_other():
    """action=focus_app with a non-browser name calls pc.focus_window."""
    with patch.object(pc, "focus_window", return_value="Focused: Code"):
        result = pc_controller({"action": "focus_app", "app": "code"})

    assert "Focused" in result


def test_action_focus_app_missing_app():
    """action=focus_app without an app name returns an error."""
    result = pc_controller({"action": "focus_app"})
    assert "Provide app name" in result


def test_action_focus_app_empty_app():
    """action=focus_app with empty app string returns an error."""
    result = pc_controller({"action": "focus_app", "app": ""})
    assert "Provide app name" in result


def test_action_close_app():
    """action=close_app delegates to pc.close_window."""
    with patch.object(pc, "close_window", return_value="Closed: Terminal"):
        result = pc_controller({"action": "close_app", "app": "terminal"})

    assert "Closed" in result


def test_action_close_app_missing_app():
    """action=close_app without an app name returns an error."""
    result = pc_controller({"action": "close_app"})
    assert "Provide app name" in result


# ---------------------------------------------------------------------------
# Browser tab
# ---------------------------------------------------------------------------


def test_action_browser_tab():
    """action=browser_tab delegates to pc.browser_tab."""
    with patch.object(pc, "browser_tab", return_value="Browser tab: next") as mock_tab:
        result = pc_controller({"action": "browser_tab", "tab_action": "next"})
        assert "Browser tab" in result
        mock_tab.assert_called_with("next")


def test_action_browser_tab_defaults_to_next():
    """action=browser_tab defaults to 'next' when tab_action is omitted."""
    with patch.object(pc, "browser_tab", return_value="Browser tab: next") as mock_tab:
        result = pc_controller({"action": "browser_tab"})
        assert "Browser tab" in result
        mock_tab.assert_called_with("next")


def test_action_browser_tab_uses_app_as_fallback():
    """action=browser_tab falls back to app field when tab_action is missing."""
    with patch.object(pc, "browser_tab", return_value="Browser tab: prev") as mock_tab:
        pc_controller({"action": "browser_tab", "app": "prev"})
        mock_tab.assert_called_with("prev")


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


def test_action_media_play():
    """action=media_play delegates to pc.media_command('play')."""
    with patch.object(pc, "media_command", return_value="Media: play.") as mock_cmd:
        result = pc_controller({"action": "media_play"})
        assert "Media" in result
        mock_cmd.assert_called_with("play")


def test_action_media_pause():
    """action=media_pause delegates to pc.media_command('pause')."""
    with patch.object(pc, "media_command", return_value="Media: pause.") as mock_cmd:
        result = pc_controller({"action": "media_pause"})
        assert "Media" in result
        mock_cmd.assert_called_with("pause")


def test_action_media_toggle():
    """action=media_toggle delegates to pc.media_command('play-pause')."""
    with patch.object(pc, "media_command", return_value="Media: play-pause.") as mock_cmd:
        result = pc_controller({"action": "media_toggle"})
        assert "Media" in result
        mock_cmd.assert_called_with("play-pause")


def test_action_media_next():
    """action=media_next delegates to pc.media_command('next')."""
    with patch.object(pc, "media_command", return_value="Media: next.") as mock_cmd:
        result = pc_controller({"action": "media_next"})
        assert "Media" in result
        mock_cmd.assert_called_with("next")


def test_action_media_prev():
    """action=media_prev delegates to pc.media_command('previous')."""
    with patch.object(pc, "media_command", return_value="Media: previous.") as mock_cmd:
        result = pc_controller({"action": "media_prev"})
        assert "Media" in result
        mock_cmd.assert_called_with("previous")


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------


def test_unknown_action():
    """An unrecognized action returns a helpful error listing known actions."""
    result = pc_controller({"action": "restart"})
    assert "Unknown action" in result
    assert "volume_set" in result or "time" in result


def test_empty_action():
    """An empty action string is treated as unknown."""
    result = pc_controller({"action": ""})
    assert "Unknown action" in result


def test_missing_action():
    """A missing action key defaults to empty and returns unknown."""
    result = pc_controller({"value": 50})
    assert "Unknown action" in result


# ---------------------------------------------------------------------------
# player parameter
# ---------------------------------------------------------------------------


def test_with_player():
    """pc_controller writes a log via player when provided."""
    mock_player = MagicMock()
    with patch.object(pc, "system_status_report", return_value="=== PC status ==="):
        pc_controller({"action": "status"}, player=mock_player)

    mock_player.write_log.assert_called_once()
    assert "status" in mock_player.write_log.call_args[0][0].lower()


def test_with_player_volume_set():
    """pc_controller writes a log for volume set actions."""
    mock_player = MagicMock()
    with patch.object(pc, "volume_set", return_value="Volume set to 30%."):
        pc_controller(
            {"action": "volume_set", "value": 30}, player=mock_player
        )

    mock_player.write_log.assert_called_once()
    assert "volume_set" in mock_player.write_log.call_args[0][0].lower()
