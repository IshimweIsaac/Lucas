"""Tests for actions/computer_control.py — general computer control tool."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions import computer_control as _cc_mod
from actions.computer_control import (
    TOOL_SCHEMA,
    _click,
    _focus_window,
    _hotkey,
    _move,
    _press,
    _random_data,
    _require_pyautogui,
    _safe_screenshot_path,
    _scroll,
    _type,
    _user_profile,
    computer_control,
)


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_name():
    assert TOOL_SCHEMA["name"] == "computer_control"


def test_tool_schema_description():
    assert "type" in TOOL_SCHEMA["description"]
    assert "press" in TOOL_SCHEMA["description"]
    assert "mouse" in TOOL_SCHEMA["description"]


def test_tool_schema_parameters():
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "action" in props
    assert "text" in props
    assert "key" in props
    assert props["action"]["type"] == "STRING"


def test_tool_schema_has_description_param():
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "description" in props
    assert props["description"]["type"] == "STRING"
    assert "screen_find" in props["description"]["description"] or "screen" in props["description"]["description"]


def test_tool_schema_required_action():
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


# ---------------------------------------------------------------------------
# computer_control() — no / unknown action
# ---------------------------------------------------------------------------


def test_no_action_returns_error():
    result = computer_control(parameters={})
    assert result == "No action specified for computer_control."


def test_empty_action_returns_error():
    result = computer_control(parameters={"action": ""})
    assert result == "No action specified for computer_control."


def test_none_parameters_returns_error():
    result = computer_control(parameters=None)
    assert result == "No action specified for computer_control."


def test_unknown_action_returns_error():
    result = computer_control(parameters={"action": "fly_to_moon"})
    assert "Unknown action" in result
    assert "fly_to_moon" in result


# ---------------------------------------------------------------------------
# computer_control() — type
# ---------------------------------------------------------------------------


def test_action_type(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "type", "text": "hello"})
    assert "Typed: hello" in result
    mock_pyautogui.typewrite.assert_called_once_with("hello", interval=0.03)


def test_action_type_truncates_long_text(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    long_text = "a" * 100
    result = computer_control(parameters={"action": "type", "text": long_text})
    assert "…" in result
    assert len(result) < 130  # truncated display


# ---------------------------------------------------------------------------
# computer_control() — click actions
# ---------------------------------------------------------------------------


def test_action_click_default(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "click"})
    assert "Clicked at current position" in result
    mock_pyautogui.click.assert_called_once_with(button="left", clicks=1)


def test_action_click_with_coords(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "click", "x": 100, "y": 200}
    )
    assert "Clicked (100, 200)" in result
    mock_pyautogui.click.assert_called_once_with(100, 200, button="left", clicks=1)


def test_action_double_click(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "double_click"})
    # Without coords, it clicks at current position with clicks=2
    assert "Clicked at current position" in result
    mock_pyautogui.click.assert_called_once_with(button="left", clicks=2)


def test_action_right_click(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "right_click"})
    assert "right" in result or "button" in result


# ---------------------------------------------------------------------------
# computer_control() — move
# ---------------------------------------------------------------------------


def test_action_move(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "move", "x": 300, "y": 400}
    )
    assert "Mouse → (300, 400)" in result
    mock_pyautogui.moveTo.assert_called_once_with(300, 400, duration=0.3)


# ---------------------------------------------------------------------------
# computer_control() — hotkey
# ---------------------------------------------------------------------------


def test_action_hotkey(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "hotkey", "keys": "ctrl+c"}
    )
    assert "Hotkey: ctrl+c" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")


def test_action_hotkey_multiple_keys(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "hotkey", "keys": "ctrl+shift+esc"}
    )
    assert "Hotkey: ctrl+shift+esc" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "esc")


# ---------------------------------------------------------------------------
# computer_control() — press
# ---------------------------------------------------------------------------


def test_action_press_with_key(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "press", "key": "enter"}
    )
    assert "Pressed: enter" in result
    mock_pyautogui.press.assert_called_once_with("enter")


def test_action_press_defaults_to_enter(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "press"})
    assert "Pressed: enter" in result
    mock_pyautogui.press.assert_called_once_with("enter")


# ---------------------------------------------------------------------------
# computer_control() — scroll
# ---------------------------------------------------------------------------


def test_action_scroll_down_default(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "scroll"})
    assert "Scrolled down ×3" in result
    mock_pyautogui.scroll.assert_called_once_with(-3)


def test_action_scroll_up(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "scroll", "direction": "up", "amount": 5}
    )
    assert "Scrolled up ×5" in result
    mock_pyautogui.scroll.assert_called_once_with(5)


def test_action_scroll_down(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "scroll", "direction": "down", "amount": 10}
    )
    assert "Scrolled down ×10" in result
    mock_pyautogui.scroll.assert_called_once_with(-10)


# ---------------------------------------------------------------------------
# computer_control() — copy / paste
# ---------------------------------------------------------------------------


def test_action_copy(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    monkeypatch.setattr(_cc_mod, "_PYPERCLIP", True)
    mock_pyperclip = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyperclip", mock_pyperclip)
    mock_pyperclip.paste.return_value = "copied text"
    result = computer_control(parameters={"action": "copy"})
    assert "copied text" in result


def test_action_paste(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    monkeypatch.setattr(_cc_mod, "_PYPERCLIP", True)
    mock_pyperclip = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyperclip", mock_pyperclip)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(
        parameters={"action": "paste", "text": "hello"}
    )
    assert "Pasted: hello" in result
    mock_pyperclip.copy.assert_called_once_with("hello")


# ---------------------------------------------------------------------------
# computer_control() — wait / clear_field / current_time
# ---------------------------------------------------------------------------


def test_action_wait(monkeypatch):
    mock_time = MagicMock()
    monkeypatch.setattr(_cc_mod, "time", mock_time)
    result = computer_control(
        parameters={"action": "wait", "seconds": 2.5}
    )
    assert "Waited 2.5s" in result
    mock_time.sleep.assert_called_once_with(2.5)


def test_action_wait_clamps_to_max_30(monkeypatch):
    mock_time = MagicMock()
    monkeypatch.setattr(_cc_mod, "time", mock_time)
    computer_control(parameters={"action": "wait", "seconds": 99})
    mock_time.sleep.assert_called_once_with(30.0)


def test_action_clear_field(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = computer_control(parameters={"action": "clear_field"})
    assert "Field cleared" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "a")
    mock_pyautogui.press.assert_called_once_with("delete")


def test_action_current_time(monkeypatch):
    # computer_control does `from core import system_clock as clock` internally.
    # Use patch with create=True since core doesn't expose system_clock directly.
    with patch("core.system_clock.format_time", return_value="12:00 PM", create=True):
        result = computer_control(parameters={"action": "current_time"})
    assert "12:00 PM" in result


# ---------------------------------------------------------------------------
# computer_control() — player log
# ---------------------------------------------------------------------------


def test_with_player_writes_log(monkeypatch):
    mock_player = MagicMock()
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    computer_control(
        parameters={"action": "press", "key": "enter"},
        player=mock_player,
    )
    mock_player.write_log.assert_called_once()
    assert "press" in mock_player.write_log.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# _safe_screenshot_path
# ---------------------------------------------------------------------------


def test_safe_screenshot_path_none():
    path = _safe_screenshot_path(None)
    assert "lucas_screenshot.png" in str(path)


def test_safe_screenshot_path_valid(monkeypatch):
    # Use a path under home
    home = Path.home()
    valid = str(home / "Pictures" / "test.png")
    path = _safe_screenshot_path(valid)
    assert path == Path(valid).resolve()


def test_safe_screenshot_path_invalid_outside_home():
    path = _safe_screenshot_path("/etc/passwd.png")
    assert "lucas_screenshot.png" in str(path)


def test_safe_screenshot_path_empty_string():
    path = _safe_screenshot_path("")
    assert "lucas_screenshot.png" in str(path)


# ---------------------------------------------------------------------------
# _random_data
# ---------------------------------------------------------------------------


def test_random_data_first_name():
    result = _random_data("first_name")
    assert isinstance(result, str)
    assert len(result) > 0


def test_random_data_last_name():
    result = _random_data("last_name")
    assert isinstance(result, str)
    assert len(result) > 0


def test_random_data_name():
    result = _random_data("name")
    assert " " in result


def test_random_data_email():
    result = _random_data("email")
    assert "@" in result
    assert "." in result


def test_random_data_username():
    result = _random_data("username")
    assert isinstance(result, str)
    assert len(result) > 3


def test_random_data_password():
    result = _random_data("password")
    assert len(result) >= 12
    # Should have at least one uppercase, one digit, one special char
    assert any(c.isupper() for c in result)
    assert any(c.isdigit() for c in result)
    assert any(c in "!@#$%" for c in result)


def test_random_data_phone():
    result = _random_data("phone")
    assert result.startswith("+1")
    # +1 + 3-digit area + 7-digit number = 12 chars total
    assert len(result) == 12


def test_random_data_birthday():
    result = _random_data("birthday")
    parts = result.split("/")
    assert len(parts) == 3
    assert 1 <= int(parts[0]) <= 12
    assert 1 <= int(parts[1]) <= 28
    assert 1980 <= int(parts[2]) <= 2000


def test_random_data_address():
    result = _random_data("address")
    assert any(c.isdigit() for c in result)


def test_random_data_zip_code():
    result = _random_data("zip_code")
    assert result.isdigit()
    assert len(result) == 5


def test_random_data_city():
    result = _random_data("city")
    assert isinstance(result, str)
    assert len(result) > 0


def test_random_data_unknown_type():
    result = _random_data("unknown_type")
    assert "random_unknown_type_" in result


# ---------------------------------------------------------------------------
# _user_profile
# ---------------------------------------------------------------------------


def test_user_profile_no_file(monkeypatch):
    monkeypatch.setattr(
        _cc_mod, "_MEMORY_PATH",
        Path("/nonexistent/path/long_term.json"),
    )
    result = _user_profile()
    assert result == {}


def test_user_profile_with_data(tmp_path, monkeypatch):
    mem_file = tmp_path / "memory" / "long_term.json"
    mem_file.parent.mkdir(parents=True)
    mem_file.write_text(
        json.dumps(
            {
                "identity": {
                    "name": {"value": "Alice"},
                    "email": {"value": "alice@test.com"},
                }
            }
        )
    )
    monkeypatch.setattr(_cc_mod, "_MEMORY_PATH", mem_file)
    result = _user_profile()
    assert result == {"name": "Alice", "email": "alice@test.com"}


def test_user_profile_empty_identity(tmp_path, monkeypatch):
    mem_file = tmp_path / "memory" / "long_term.json"
    mem_file.parent.mkdir(parents=True)
    mem_file.write_text(json.dumps({"identity": {}}))
    monkeypatch.setattr(_cc_mod, "_MEMORY_PATH", mem_file)
    result = _user_profile()
    assert result == {}


def test_user_profile_corrupted_json(tmp_path, monkeypatch):
    mem_file = tmp_path / "memory" / "long_term.json"
    mem_file.parent.mkdir(parents=True)
    mem_file.write_text("not json")
    monkeypatch.setattr(_cc_mod, "_MEMORY_PATH", mem_file)
    result = _user_profile()
    assert result == {}


# ---------------------------------------------------------------------------
# _focus_window
# ---------------------------------------------------------------------------


def test_focus_window_linux_wmctrl_ok(monkeypatch):
    mock_get_os = MagicMock(return_value="linux")
    monkeypatch.setattr(_cc_mod, "_get_os", mock_get_os)
    mock_subprocess = MagicMock()
    mock_subprocess.run.return_value.returncode = 0
    monkeypatch.setattr(_cc_mod, "subprocess", mock_subprocess)
    result = _focus_window("Firefox")
    assert "Focused window: Firefox" in result
    mock_subprocess.run.assert_called_once_with(
        ["wmctrl", "-a", "Firefox"],
        capture_output=True, timeout=5,
    )


def test_focus_window_linux_wmctrl_not_found(monkeypatch):
    mock_get_os = MagicMock(return_value="linux")
    monkeypatch.setattr(_cc_mod, "_get_os", mock_get_os)

    mock_subprocess = MagicMock()

    def side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "wmctrl" in str(cmd):
            result = MagicMock()
            result.returncode = 1
            return result
        result = MagicMock()
        result.returncode = 0
        return result

    mock_subprocess.run.side_effect = side_effect
    monkeypatch.setattr(_cc_mod, "subprocess", mock_subprocess)
    result = _focus_window("Firefox")
    assert "Focused window: Firefox" in result
    assert mock_subprocess.run.call_count >= 2


def test_focus_window_linux_no_wmctrl_no_xdotool(monkeypatch):
    mock_get_os = MagicMock(return_value="linux")
    monkeypatch.setattr(_cc_mod, "_get_os", mock_get_os)

    mock_subprocess = MagicMock()
    mock_subprocess.run.side_effect = FileNotFoundError("not found")
    monkeypatch.setattr(_cc_mod, "subprocess", mock_subprocess)
    result = _focus_window("Firefox")
    assert "requires wmctrl or xdotool" in result


def test_focus_window_unknown_os(monkeypatch):
    mock_get_os = MagicMock(return_value="solaris")
    monkeypatch.setattr(_cc_mod, "_get_os", mock_get_os)
    result = _focus_window("Firefox")
    assert "unknown OS" in result


# ---------------------------------------------------------------------------
# _require_pyautogui
# ---------------------------------------------------------------------------


def test_require_pyautogui_ok(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    _require_pyautogui()


def test_require_pyautogui_raises(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", False)
    with pytest.raises(RuntimeError, match="PyAutoGUI not installed"):
        _require_pyautogui()


# ---------------------------------------------------------------------------
# _type
# ---------------------------------------------------------------------------


def test_type_function(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _type("hello")
    assert "Typed: hello" in result
    mock_pyautogui.typewrite.assert_called_once_with("hello", interval=0.03)


def test_type_function_truncates_long(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    long_text = "x" * 100
    result = _type(long_text)
    assert "…" in result


def test_type_requires_pyautogui(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", False)
    with pytest.raises(RuntimeError, match="PyAutoGUI not installed"):
        _type("hello")


# ---------------------------------------------------------------------------
# _click
# ---------------------------------------------------------------------------


def test_click_function(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _click(100, 200)
    assert "Clicked (100, 200)" in result
    mock_pyautogui.click.assert_called_once_with(100, 200, button="left", clicks=1)


# ---------------------------------------------------------------------------
# _hotkey
# ---------------------------------------------------------------------------


def test_hotkey_function(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _hotkey("ctrl", "c")
    assert "Hotkey: ctrl+c" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")


# ---------------------------------------------------------------------------
# _press
# ---------------------------------------------------------------------------


def test_press_function(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _press("tab")
    assert "Pressed: tab" in result
    mock_pyautogui.press.assert_called_once_with("tab")


# ---------------------------------------------------------------------------
# _scroll
# ---------------------------------------------------------------------------


def test_scroll_function_down(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _scroll("down", 3)
    assert "Scrolled down ×3" in result
    mock_pyautogui.scroll.assert_called_once_with(-3)


def test_scroll_function_up(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _scroll("up", 5)
    assert "Scrolled up ×5" in result
    mock_pyautogui.scroll.assert_called_once_with(5)


def test_scroll_function_right(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _scroll("right", 2)
    assert "Scrolled right ×2" in result
    mock_pyautogui.hscroll.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# _move
# ---------------------------------------------------------------------------


def test_move_function(monkeypatch):
    monkeypatch.setattr(_cc_mod, "_PYAUTOGUI", True)
    mock_pyautogui = MagicMock()
    monkeypatch.setattr(_cc_mod, "pyautogui", mock_pyautogui, raising=False)
    result = _move(800, 600)
    assert "Mouse → (800, 600)" in result
    mock_pyautogui.moveTo.assert_called_once_with(800, 600, duration=0.3)


# ---------------------------------------------------------------------------
# screen_find / screen_click — grounded via the router
# ---------------------------------------------------------------------------


def _fake_result(found, x=0, y=0, source="a11y", label="", note=""):
    return type(
        "GroundingResult",
        (),
        {
            "found": found,
            "x": x,
            "y": y,
            "source": source,
            "label": label,
            "note": note,
        },
    )()


def test_screen_find_returns_coords_via_router(monkeypatch):
    monkeypatch.setattr(_cc_mod, "resolve_intent", lambda desc: _fake_result(True, 100, 200))
    result = computer_control(parameters={"action": "screen_find", "description": "Save"})
    assert result == "100,200"


def test_screen_find_not_found(monkeypatch):
    monkeypatch.setattr(_cc_mod, "resolve_intent", lambda desc: _fake_result(False))
    result = computer_control(parameters={"action": "screen_find", "description": "Ghost"})
    assert result == "NOT_FOUND"


def test_screen_find_empty_target_no_network(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(_cc_mod, "resolve_intent", lambda desc: calls.__setitem__("n", calls["n"] + 1) or _fake_result(False))
    result = computer_control(parameters={"action": "screen_find", "description": ""})
    assert result == "NOT_FOUND (no target text)"
    assert calls["n"] == 0


def test_screen_click_routes_through_router(monkeypatch):
    seen = {}

    def fake_router(desc, click_fn=None):
        seen["desc"] = desc
        seen["click_fn"] = click_fn
        return "route-return"

    monkeypatch.setattr(_cc_mod, "router_click", fake_router)
    result = computer_control(parameters={"action": "screen_click", "description": "Save"})
    assert result == "route-return"
    assert seen["desc"] == "Save"
    assert callable(seen["click_fn"])


def test_screen_click_router_calls_click(monkeypatch):
    click_spy = MagicMock()
    monkeypatch.setattr(_cc_mod, "_click", click_spy)

    def fake_router(desc, click_fn=None):
        click_fn(100, 200)
        return "Clicked 'Save' at (100,200) via a11y"

    monkeypatch.setattr(_cc_mod, "router_click", fake_router)
    result = computer_control(parameters={"action": "screen_click", "description": "Save"})
    assert result == "Clicked 'Save' at (100,200) via a11y"
    click_spy.assert_called_once_with(100, 200)
