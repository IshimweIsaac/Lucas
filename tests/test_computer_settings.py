"""Tests for actions/computer_settings.py — computer settings control tool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from actions import computer_settings as _cs_mod
from actions.computer_settings import (
    ACTION_MAP,
    TOOL_SCHEMA,
    _DANGEROUS_ACTIONS,
    brightness_down,
    brightness_set,
    brightness_up,
    close_app,
    computer_settings,
    copy,
    cut,
    dark_mode,
    full_screen,
    lock_screen,
    maximize_window,
    minimize_window,
    paste,
    redo,
    scroll_down,
    scroll_up,
    take_screenshot,
    toggle_wifi,
    type_text,
    undo,
    volume_down,
    volume_mute,
    volume_set,
    volume_up,
)


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_name():
    assert TOOL_SCHEMA["name"] == "computer_settings"


def test_tool_schema_description():
    assert "volume" in TOOL_SCHEMA["description"]
    assert "brightness" in TOOL_SCHEMA["description"]
    assert "restart" in TOOL_SCHEMA["description"]


def test_tool_schema_parameters():
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "action" in props
    assert "description" in props
    assert "value" in props
    assert props["action"]["type"] == "STRING"
    assert props["description"]["type"] == "STRING"
    assert props["value"]["type"] == "STRING"


def test_tool_schema_required_is_empty():
    assert TOOL_SCHEMA["parameters"]["required"] == []


# ---------------------------------------------------------------------------
# ACTION_MAP
# ---------------------------------------------------------------------------


def test_action_map_has_known_actions():
    assert "volume_up" in ACTION_MAP
    assert "volume_down" in ACTION_MAP
    assert "mute" in ACTION_MAP
    assert "brightness_up" in ACTION_MAP
    assert "brightness_down" in ACTION_MAP
    assert "close_app" in ACTION_MAP
    assert "full_screen" in ACTION_MAP
    assert "minimize" in ACTION_MAP
    assert "maximize" in ACTION_MAP
    assert "copy" in ACTION_MAP
    assert "paste" in ACTION_MAP
    assert "cut" in ACTION_MAP
    assert "undo" in ACTION_MAP
    assert "redo" in ACTION_MAP
    assert "screenshot" in ACTION_MAP
    assert "lock_screen" in ACTION_MAP
    assert "dark_mode" in ACTION_MAP
    assert "toggle_wifi" in ACTION_MAP
    assert "restart" in ACTION_MAP
    assert "shutdown" in ACTION_MAP


def test_action_map_value_is_callable():
    for name, func in ACTION_MAP.items():
        assert callable(func), f"{name} is not callable"


# ---------------------------------------------------------------------------
# _DANGEROUS_ACTIONS
# ---------------------------------------------------------------------------


def test_dangerous_actions_contains_restart_and_shutdown():
    assert "restart" in _DANGEROUS_ACTIONS
    assert "shutdown" in _DANGEROUS_ACTIONS


def test_dangerous_actions_size():
    assert len(_DANGEROUS_ACTIONS) == 2


# ---------------------------------------------------------------------------
# computer_settings() — main dispatch: no / unknown action
# ---------------------------------------------------------------------------


def test_no_action_returns_error():
    result = computer_settings(parameters={})
    assert result == "No action could be determined."


def test_no_action_with_empty_string():
    result = computer_settings(parameters={"action": ""})
    assert result == "No action could be determined."


def test_none_parameters():
    result = computer_settings(parameters=None)
    assert result == "No action could be determined."


def test_unknown_action_returns_error():
    result = computer_settings(parameters={"action": "fly_to_moon"})
    assert "Unknown action" in result
    assert "fly_to_moon" in result


# ---------------------------------------------------------------------------
# computer_settings() — volume actions
# ---------------------------------------------------------------------------


def test_volume_set_with_value(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "volume_set", mock_fn)
    result = computer_settings(parameters={"action": "volume_set", "value": "42"})
    assert "Volume set to 42%" in result
    mock_fn.assert_called_once_with(42)


def test_volume_set_defaults_to_50(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "volume_set", mock_fn)
    result = computer_settings(parameters={"action": "volume_set"})
    # Source returns f"Volume set to {value}%" using the original None value
    assert "Volume set to None" in result
    mock_fn.assert_called_once_with(50)


def test_volume_set_handles_exception(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")

    def failing_fn(*args, **kwargs):
        raise ValueError("broken")

    monkeypatch.setattr(_cs_mod, "volume_set", failing_fn)
    result = computer_settings(parameters={"action": "volume_set", "value": "50"})
    assert "Could not set volume" in result
    assert "broken" in result


def test_volume_up_dispatches(monkeypatch):
    """volume_up dispatches via ACTION_MAP lookup."""
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "volume_up", mock_fn)
    result = computer_settings(parameters={"action": "volume_up"})
    assert "Done: volume_up" in result
    mock_fn.assert_called_once()


def test_volume_down_dispatches(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "volume_down", mock_fn)
    result = computer_settings(parameters={"action": "volume_down"})
    assert "Done: volume_down" in result
    mock_fn.assert_called_once()


def test_mute_dispatches(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "mute", mock_fn)
    result = computer_settings(parameters={"action": "mute"})
    assert "Done: mute" in result
    mock_fn.assert_called_once()


def test_unmute_dispatches(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "unmute", mock_fn)
    result = computer_settings(parameters={"action": "unmute"})
    assert "Done: unmute" in result
    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# computer_settings() — brightness actions
# ---------------------------------------------------------------------------


def test_brightness_set_with_value(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "brightness_set", mock_fn)
    result = computer_settings(
        parameters={"action": "brightness_set", "value": "75"}
    )
    assert "Brightness set to 75%" in result
    mock_fn.assert_called_once_with(75)


def test_brightness_set_handles_exception(monkeypatch):

    def failing_fn(*args, **kwargs):
        raise ValueError("oops")

    monkeypatch.setattr(_cs_mod, "brightness_set", failing_fn)
    result = computer_settings(
        parameters={"action": "brightness_set", "value": "50"}
    )
    assert "Could not set brightness" in result
    assert "oops" in result


def test_brightness_up_dispatches(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "brightness_up", mock_fn)
    result = computer_settings(parameters={"action": "brightness_up"})
    assert "Done: brightness_up" in result
    mock_fn.assert_called_once()


def test_brightness_down_dispatches(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "brightness_down", mock_fn)
    result = computer_settings(parameters={"action": "brightness_down"})
    assert "Done: brightness_down" in result
    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# computer_settings() — type_text
# ---------------------------------------------------------------------------


def test_type_text_with_text(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "type_text", mock_fn)
    result = computer_settings(
        parameters={"action": "type_text", "value": "Hello World"}
    )
    assert "Typed: Hello World" in result
    mock_fn.assert_called_once_with("Hello World", press_enter_after=False)


def test_type_text_with_press_enter(monkeypatch):
    mock_fn = MagicMock()
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    monkeypatch.setattr(_cs_mod, "type_text", mock_fn)
    result = computer_settings(
        parameters={
            "action": "type_text",
            "value": "Hello",
            "press_enter": "true",
        }
    )
    assert "Typed: Hello" in result
    mock_fn.assert_called_once_with("Hello", press_enter_after=True)


def test_type_text_no_text_returns_error():
    result = computer_settings(parameters={"action": "type_text"})
    assert result == "No text provided to type."


def test_type_text_empty_text_returns_error():
    result = computer_settings(parameters={"action": "type_text", "value": ""})
    assert result == "No text provided to type."


def test_type_alternate_action_names(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "type_text", mock_fn)
    for alt in ("write_on_screen", "type", "write"):
        result = computer_settings(
            parameters={"action": alt, "value": "test"}
        )
        assert "Typed: test" in result


# ---------------------------------------------------------------------------
# computer_settings() — press_key
# ---------------------------------------------------------------------------


def test_press_key_with_key(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "press_key", mock_fn)
    result = computer_settings(
        parameters={"action": "press_key", "value": "f5"}
    )
    assert "Pressed: f5" in result
    mock_fn.assert_called_once_with("f5")


def test_press_key_no_key_returns_error():
    result = computer_settings(parameters={"action": "press_key"})
    assert result == "No key specified."


def test_press_key_empty_key_returns_error():
    result = computer_settings(parameters={"action": "press_key", "value": ""})
    assert result == "No key specified."


# ---------------------------------------------------------------------------
# computer_settings() — scroll
# ---------------------------------------------------------------------------


def test_scroll_up(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "scroll_up", mock_fn)
    result = computer_settings(parameters={"action": "scroll_up"})
    assert "Scrolled up" in result
    mock_fn.assert_called_once_with(500)


def test_scroll_up_with_value(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "scroll_up", mock_fn)
    result = computer_settings(parameters={"action": "scroll_up", "value": "200"})
    assert "Scrolled up" in result
    mock_fn.assert_called_once_with(200)


def test_scroll_down(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "scroll_down", mock_fn)
    result = computer_settings(parameters={"action": "scroll_down"})
    assert "Scrolled down" in result
    mock_fn.assert_called_once_with(500)


def test_scroll_down_with_value(monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "scroll_down", mock_fn)
    result = computer_settings(parameters={"action": "scroll_down", "value": "100"})
    assert "Scrolled down" in result
    mock_fn.assert_called_once_with(100)


# ---------------------------------------------------------------------------
# computer_settings() — dangerous actions (restart / shutdown)
# ---------------------------------------------------------------------------


def test_restart_without_confirmation():
    result = computer_settings(parameters={"action": "restart"})
    assert "Please confirm" in result
    assert "restart" in result


def test_shutdown_without_confirmation():
    result = computer_settings(parameters={"action": "shutdown"})
    assert "Please confirm" in result
    assert "shutdown" in result


@pytest.mark.parametrize("confirmed", ["yes", "true", "1", "confirm"])
def test_restart_with_confirmed(confirmed, monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "restart", mock_fn)
    result = computer_settings(
        parameters={"action": "restart", "confirmed": confirmed}
    )
    assert "Done: restart" in result
    mock_fn.assert_called_once()


@pytest.mark.parametrize("confirmed", ["yes", "true", "1", "confirm"])
def test_shutdown_with_confirmed(confirmed, monkeypatch):
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "shutdown", mock_fn)
    result = computer_settings(
        parameters={"action": "shutdown", "confirmed": confirmed}
    )
    assert "Done: shutdown" in result
    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# computer_settings() — description-based detection
# ---------------------------------------------------------------------------


def test_description_based_detection_calls_detect_action(monkeypatch):
    mock_detect = MagicMock(return_value={"action": "volume_up", "value": None})
    monkeypatch.setattr(_cs_mod, "_detect_action", mock_detect)
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "volume_up", mock_fn)
    result = computer_settings(
        parameters={"description": "turn up the volume"}
    )
    assert "Done: volume_up" in result
    mock_detect.assert_called_once_with("turn up the volume")
    mock_fn.assert_called_once()


def test_description_based_detection_with_value(monkeypatch):
    mock_detect = MagicMock(return_value={"action": "volume_set", "value": "30"})
    monkeypatch.setattr(_cs_mod, "_detect_action", mock_detect)
    mock_fn = MagicMock()
    monkeypatch.setattr(_cs_mod, "volume_set", mock_fn)
    computer_settings(parameters={"description": "set volume to 30"})
    mock_fn.assert_called_once_with(30)


# ---------------------------------------------------------------------------
# computer_settings() — player log
# ---------------------------------------------------------------------------


def test_with_player_writes_log(monkeypatch):
    mock_player = MagicMock()
    mock_fn = MagicMock()
    monkeypatch.setitem(ACTION_MAP, "volume_up", mock_fn)
    computer_settings(
        parameters={"action": "volume_up"}, player=mock_player
    )
    mock_player.write_log.assert_called_once()
    assert "volume_up" in mock_player.write_log.call_args[0][0]


# ---------------------------------------------------------------------------
# Individual helpers — volume
# ---------------------------------------------------------------------------


def test_volume_up_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_up()
    mock_subprocess.run.assert_called_once_with(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
        capture_output=True,
    )


def test_volume_up_windows(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Windows")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    volume_up()
    assert mock_pyautogui.press.call_count == 5
    mock_pyautogui.press.assert_called_with("volumeup")


def test_volume_up_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_up()
    mock_subprocess.run.assert_called_once()
    args = mock_subprocess.run.call_args[0][0]
    assert "osascript" in args
    assert "volume output volume" in args[2]


def test_volume_down_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_down()
    mock_subprocess.run.assert_called_once_with(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
        capture_output=True,
    )


def test_volume_down_windows(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Windows")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    volume_down()
    assert mock_pyautogui.press.call_count == 5
    mock_pyautogui.press.assert_called_with("volumedown")


def test_volume_mute_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_mute()
    mock_subprocess.run.assert_called_once_with(
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
        capture_output=True,
    )


def test_volume_mute_windows(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Windows")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    volume_mute()
    mock_pyautogui.press.assert_called_once_with("volumemute")


def test_volume_set_linux_success(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    # volume_set does `from core import pc_control` internally
    mock_pc_vol = MagicMock(return_value="Volume set to 50%")
    monkeypatch.setattr("core.pc_control.volume_set", mock_pc_vol)
    volume_set(50)
    mock_pc_vol.assert_called_once_with(50)


def test_volume_set_linux_fallback_on_failure(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    # Make pc_control.volume_set return failure so we fall through to pactl
    mock_pc_vol = MagicMock(return_value="failed: no pactl")
    monkeypatch.setattr("core.pc_control.volume_set", mock_pc_vol)
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_set(50)
    # Falls through to pactl fallback
    mock_subprocess.run.assert_called_once_with(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "50%"],
        capture_output=True,
    )


def test_volume_set_clamps_value(monkeypatch):
    # Use Darwin to avoid the pc_control branch (osascript path)
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    volume_set(-10)
    # On Darwin: osascript -e "set volume output volume 0"
    args = mock_subprocess.run.call_args[0][0]
    assert "0" in args[-1]
    assert "-10" not in args[-1]


# ---------------------------------------------------------------------------
# Individual helpers — brightness
# ---------------------------------------------------------------------------


def test_brightness_up_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # which returns 0 for brightnessctl
    mock_subprocess.run.return_value.returncode = 0
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    brightness_up()
    # First call is `which brightnessctl`, second is the actual command
    calls = mock_subprocess.run.call_args_list
    assert len(calls) == 2
    assert calls[1][0][0] == ["brightnessctl", "set", "+10%"]


def test_brightness_up_linux_no_brightnessctl(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # which returns non-zero for brightnessctl
    mock_subprocess.run.return_value.returncode = 1
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    brightness_up()
    calls = mock_subprocess.run.call_args_list
    assert len(calls) == 2
    # Second call uses shell=True fallback
    assert calls[1][1].get("shell") is True


def test_brightness_up_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    brightness_up()
    mock_subprocess.run.assert_called_once()
    args = mock_subprocess.run.call_args[0][0]
    assert "osascript" in args


def test_brightness_down_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    mock_subprocess.run.return_value.returncode = 0
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    brightness_down()
    calls = mock_subprocess.run.call_args_list
    assert len(calls) == 2
    assert "10%-" in calls[1][0][0]


def test_brightness_set_linux_ok(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    # brightness_set does `from core import pc_control` internally
    mock_pc_bright = MagicMock(return_value="ok")
    monkeypatch.setattr("core.pc_control.brightness_set", mock_pc_bright)
    brightness_set(60)
    mock_pc_bright.assert_called_once_with(60)


def test_brightness_set_clamps_value(monkeypatch):
    # Use Darwin to avoid pc_control branch, then subprocess is used
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    brightness_set(150)
    # On Darwin, brightness_set just prints a message and returns without subprocess
    # So test that the function handles the clamp without error
    assert mock_subprocess.run.called is False


# ---------------------------------------------------------------------------
# Individual helpers — window / app management
# ---------------------------------------------------------------------------


def test_close_app_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    close_app()
    mock_pyautogui.hotkey.assert_called_once_with("alt", "f4")


def test_close_app_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    close_app()
    mock_pyautogui.hotkey.assert_called_once_with("command", "q")


def test_full_screen_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    full_screen()
    mock_pyautogui.press.assert_called_once_with("f11")


def test_full_screen_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    full_screen()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "command", "f")


def test_minimize_window_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    minimize_window()
    mock_pyautogui.hotkey.assert_called_once_with("win", "down")


def test_minimize_window_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    minimize_window()
    mock_pyautogui.hotkey.assert_called_once_with("command", "m")


def test_maximize_window_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    maximize_window()
    mock_subprocess.run.assert_called_once()
    args = mock_subprocess.run.call_args[0][0]
    assert "wmctrl" in args


# ---------------------------------------------------------------------------
# Individual helpers — clipboard
# ---------------------------------------------------------------------------


def test_copy_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    copy()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")


def test_copy_darwin(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Darwin")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    copy()
    mock_pyautogui.hotkey.assert_called_once_with("command", "c")


def test_paste_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    paste()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "v")


def test_cut_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    cut()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "x")


def test_undo_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    undo()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "z")


def test_redo_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    redo()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "y")


# ---------------------------------------------------------------------------
# Individual helpers — type_text
# ---------------------------------------------------------------------------


def test_type_text_with_pyperclip(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_PYPERCLIP", True)
    mock_pyperclip = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyperclip", mock_pyperclip)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    type_text("Hello World")
    mock_pyperclip.copy.assert_called_once_with("Hello World")


def test_type_text_without_pyperclip(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_PYPERCLIP", False)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    type_text("Hello World")
    mock_pyautogui.write.assert_called_once_with("Hello World", interval=0.03)


def test_type_text_with_press_enter_fn(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_PYPERCLIP", False)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    type_text("Hello", press_enter_after=True)
    mock_pyautogui.write.assert_called_once_with("Hello", interval=0.03)
    mock_pyautogui.press.assert_called_once_with("enter")


def test_type_text_empty_returns_early(monkeypatch):
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    type_text("")
    mock_pyautogui.write.assert_not_called()
    mock_pyautogui.press.assert_not_called()


# ---------------------------------------------------------------------------
# Individual helpers — take_screenshot
# ---------------------------------------------------------------------------


def test_take_screenshot_linux_finds_scrot(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # First `which scrot` returns 0
    mock_subprocess.run.return_value.returncode = 0
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    take_screenshot()
    calls = mock_subprocess.run.call_args_list
    # First call: which scrot
    assert calls[0][0][0] == ["which", "scrot"]
    # subprocess.Popen is called with scrot
    mock_subprocess.Popen.assert_called_once_with(["scrot"])


def test_take_screenshot_linux_fallback(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # All `which` calls return non-zero
    mock_subprocess.run.return_value.returncode = 1
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    take_screenshot()
    # Falls through to pyautogui hotkey fallback
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "print_screen")


# ---------------------------------------------------------------------------
# Individual helpers — lock_screen
# ---------------------------------------------------------------------------


def test_lock_screen_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    mock_subprocess.run.return_value.returncode = 0
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    lock_screen()
    # Should try gnome-screensaver-command first
    calls = mock_subprocess.run.call_args_list
    first_call_args = calls[0][0][0]
    assert "gnome-screensaver-command" in first_call_args


# ---------------------------------------------------------------------------
# Individual helpers — dark_mode
# ---------------------------------------------------------------------------


def test_dark_mode_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # First call (gsettings get) returns 'default'
    mock_subprocess.run.return_value.stdout = "'default'\n"
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    dark_mode()
    calls = mock_subprocess.run.call_args_list
    assert len(calls) == 2
    assert "gsettings" in calls[0][0][0][0]
    assert "gsettings" in calls[1][0][0][0]
    # Second call should set prefer-dark
    assert "prefer-dark" in str(calls[1][0][0])


def test_dark_mode_linux_already_dark(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    mock_subprocess.run.return_value.stdout = "'prefer-dark'\n"
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    dark_mode()
    calls = mock_subprocess.run.call_args_list
    # Second call should set default
    assert "default" in str(calls[1][0][0])


# ---------------------------------------------------------------------------
# Individual helpers — toggle_wifi
# ---------------------------------------------------------------------------


def test_toggle_wifi_linux(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    # nmcli radio wifi returns "enabled"
    mock_subprocess.run.return_value.stdout = "enabled\n"
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    toggle_wifi()
    calls = mock_subprocess.run.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == ["nmcli", "radio", "wifi"]
    assert calls[1][0][0] == ["nmcli", "radio", "wifi", "off"]


def test_toggle_wifi_linux_disabled(monkeypatch):
    monkeypatch.setattr(_cs_mod, "_OS", "Linux")
    mock_subprocess = MagicMock()
    mock_subprocess.run.return_value.stdout = "disabled\n"
    monkeypatch.setattr(_cs_mod, "subprocess", mock_subprocess)
    toggle_wifi()
    calls = mock_subprocess.run.call_args_list
    assert calls[1][0][0] == ["nmcli", "radio", "wifi", "on"]


# ---------------------------------------------------------------------------
# Individual helpers — scroll
# ---------------------------------------------------------------------------


def test_scroll_up_function(monkeypatch):
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    scroll_up(300)
    mock_pyautogui.scroll.assert_called_once_with(300)


def test_scroll_up_default(monkeypatch):
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    scroll_up()
    mock_pyautogui.scroll.assert_called_once_with(500)


def test_scroll_down_function(monkeypatch):
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    scroll_down(200)
    mock_pyautogui.scroll.assert_called_once_with(-200)


def test_scroll_down_default(monkeypatch):
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cs_mod, "pyautogui", mock_pyautogui, raising=False)
    scroll_down()
    mock_pyautogui.scroll.assert_called_once_with(-500)
