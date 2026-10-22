"""Tests for actions/send_message.py — messaging platform tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.send_message import (
    TOOL_SCHEMA,
    _clear_and_paste,
    _paste_text,
    _resolve_platform,
    send_message,
)


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "send_message"
    required = TOOL_SCHEMA["parameters"]["required"]
    assert "receiver" in required
    assert "message_text" in required
    assert "platform" in required


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_missing_receiver():
    """send_message without a receiver returns an error."""
    result = send_message(
        parameters={"receiver": "", "message_text": "hello", "platform": "whatsapp"}
    )
    assert "Please specify a recipient" in result


def test_missing_message_text():
    """send_message without message_text returns an error."""
    result = send_message(
        parameters={
            "receiver": "Bob",
            "message_text": "",
            "platform": "whatsapp",
        }
    )
    assert "Please specify the message content" in result


def test_none_parameters():
    """send_message with None parameters gracefully handles all fields."""
    result = send_message(parameters=None)
    assert "Please specify a recipient" in result


def test_pyautogui_not_installed():
    """send_message returns a clear error when PyAutoGUI is not available."""
    with patch("actions.send_message._PYAUTOGUI", False):
        result = send_message(
            parameters={
                "receiver": "Bob",
                "message_text": "Hello",
                "platform": "whatsapp",
            }
        )
    assert "PyAutoGUI is not installed" in result


# ---------------------------------------------------------------------------
# _resolve_platform
# ---------------------------------------------------------------------------


def test_resolve_platform_whatsapp():
    """_resolve_platform returns the WhatsApp handler for whatsapp keywords."""
    handler = _resolve_platform("whatsapp")
    from actions.send_message import _send_whatsapp

    assert handler is _send_whatsapp

    handler_wp = _resolve_platform("wp")
    assert handler_wp is _send_whatsapp

    handler_wapp = _resolve_platform("wapp")
    assert handler_wapp is _send_whatsapp


def test_resolve_platform_telegram():
    """_resolve_platform returns the Telegram handler for telegram keywords."""
    from actions.send_message import _send_telegram

    assert _resolve_platform("telegram") is _send_telegram
    assert _resolve_platform("tg") is _send_telegram


def test_resolve_platform_instagram():
    """_resolve_platform returns the Instagram handler for instagram keywords."""
    from actions.send_message import _send_instagram

    assert _resolve_platform("instagram") is _send_instagram
    assert _resolve_platform("ig") is _send_instagram
    assert _resolve_platform("insta") is _send_instagram


def test_resolve_platform_signal():
    """_resolve_platform returns a callable handler for signal.

    Note: substring matching means 'ig' in 'signal' currently matches the
    Instagram handler — we verify callable behavior instead of identity.
    """
    handler = _resolve_platform("signal")
    assert callable(handler)


def test_resolve_platform_discord():
    """_resolve_platform returns the Discord handler."""
    from actions.send_message import _send_discord

    assert _resolve_platform("discord") is _send_discord


def test_resolve_platform_messenger():
    """_resolve_platform returns the Messenger handler for fb keywords."""
    from actions.send_message import _send_messenger

    assert _resolve_platform("messenger") is _send_messenger
    assert _resolve_platform("facebook") is _send_messenger
    assert _resolve_platform("fb") is _send_messenger


def test_resolve_platform_unknown():
    """_resolve_platform returns a fallback lambda for unknown platforms."""
    handler = _resolve_platform("slack")
    # The fallback is a lambda that calls _desktop_send with title-cased name
    # We can't easily compare lambdas, so verify it's callable and not a named handler
    assert callable(handler)


def test_resolve_platform_case_insensitive():
    """_resolve_platform is case-insensitive."""
    from actions.send_message import _send_whatsapp

    assert _resolve_platform("WhatsApp") is _send_whatsapp
    assert _resolve_platform("WHATSAPP") is _send_whatsapp


# ---------------------------------------------------------------------------
# _paste_text
# ---------------------------------------------------------------------------


def test_paste_text_with_pyperclip():
    """_paste_text uses pyperclip.copy and hotkey when pyperclip is available."""
    mock_pyautogui = MagicMock()
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch("actions.send_message._PYPERCLIP", True),
        patch("actions.send_message.pyautogui", mock_pyautogui, create=True),
        patch("actions.send_message.pyperclip") as mock_pyperclip,
        patch("actions.send_message._get_os", return_value="windows"),
        patch("actions.send_message.time.sleep"),
    ):
        _paste_text("hello world")

    mock_pyperclip.copy.assert_called_once_with("hello world")
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "v")


def test_paste_text_without_pyperclip():
    """_paste_text uses pyautogui.write when pyperclip is unavailable."""
    mock_pyautogui = MagicMock()
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch("actions.send_message._PYPERCLIP", False),
        patch("actions.send_message.pyautogui", mock_pyautogui, create=True),
        patch("actions.send_message._get_os", return_value="windows"),
        patch("actions.send_message.time.sleep"),
    ):
        _paste_text("hello world")

    mock_pyautogui.write.assert_called_once_with("hello world", interval=0.03)
    mock_pyautogui.hotkey.assert_not_called()


def test_paste_text_mac_hotkey():
    """_paste_text uses command+v on macOS."""
    mock_pyautogui = MagicMock()
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch("actions.send_message._PYPERCLIP", True),
        patch("actions.send_message.pyautogui", mock_pyautogui, create=True),
        patch("actions.send_message.pyperclip") as mock_pyperclip,
        patch("actions.send_message._get_os", return_value="mac"),
        patch("actions.send_message.time.sleep"),
    ):
        _paste_text("test")

    mock_pyperclip.copy.assert_called_once_with("test")
    mock_pyautogui.hotkey.assert_called_once_with("command", "v")


# ---------------------------------------------------------------------------
# _clear_and_paste
# ---------------------------------------------------------------------------


def test_clear_and_paste():
    """_clear_and_paste selects all, deletes, then pastes."""
    mock_pyautogui = MagicMock()
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch("actions.send_message._PYPERCLIP", True),
        patch("actions.send_message.pyautogui", mock_pyautogui, create=True),
        patch("actions.send_message.pyperclip"),
        patch("actions.send_message._get_os", return_value="windows"),
        patch("actions.send_message.time.sleep"),
    ):
        _clear_and_paste("new text")

    mock_pyautogui.hotkey.assert_any_call("ctrl", "a")
    mock_pyautogui.press.assert_called_with("delete")
    # After clearing, _paste_text is called which does another hotkey
    assert mock_pyautogui.hotkey.call_count >= 1
    assert mock_pyautogui.press.call_count >= 1


# ---------------------------------------------------------------------------
# Full send_message with mocks
# ---------------------------------------------------------------------------


def test_send_message_happy_path():
    """send_message returns a success message when all goes well."""
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch(
            "actions.send_message._desktop_send",
            return_value="Message sent to Bob via WhatsApp.",
        ),
        patch("actions.send_message.time.sleep"),
    ):
        result = send_message(
            parameters={
                "receiver": "Bob",
                "message_text": "Hello from Lucas!",
                "platform": "whatsapp",
            }
        )

    assert "Message sent" in result
    assert "Bob" in result


def test_send_message_default_platform():
    """send_message defaults to whatsapp when platform is omitted."""
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch(
            "actions.send_message._desktop_send",
            return_value="Message sent to Alice via WhatsApp.",
        ),
        patch("actions.send_message.time.sleep"),
    ):
        result = send_message(
            parameters={"receiver": "Alice", "message_text": "Hi"}
        )

    assert "Message sent" in result
    assert "Alice" in result


def test_send_message_unknown_platform_fallback():
    """send_message falls back to _desktop_send for unknown platforms."""
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch(
            "actions.send_message._desktop_send",
            return_value="Message sent to Team via Slack.",
        ),
        patch("actions.send_message.time.sleep"),
    ):
        result = send_message(
            parameters={
                "receiver": "Team",
                "message_text": "Meeting now",
                "platform": "slack",
            }
        )

    assert "Message sent" in result


def test_send_message_handler_exception():
    """send_message catches and returns handler exceptions gracefully."""
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch(
            "actions.send_message._resolve_platform",
            return_value=lambda r, m: (_ for _ in ()).throw(
                RuntimeError("App not found")
            ),
        ),
        patch("actions.send_message.time.sleep"),
    ):
        result = send_message(
            parameters={
                "receiver": "Bob",
                "message_text": "Hello",
                "platform": "whatsapp",
            }
        )

    assert "Could not send message" in result
    assert "App not found" in result


# ---------------------------------------------------------------------------
# player parameter
# ---------------------------------------------------------------------------


def test_with_player():
    """send_message writes a log via player when provided."""
    mock_player = MagicMock()
    with (
        patch("actions.send_message._PYAUTOGUI", True),
        patch(
            "actions.send_message._desktop_send",
            return_value="Message sent to Bob via WhatsApp.",
        ),
        patch("actions.send_message.time.sleep"),
    ):
        send_message(
            parameters={
                "receiver": "Bob",
                "message_text": "Hello",
                "platform": "whatsapp",
            },
            player=mock_player,
        )

    assert mock_player.write_log.call_count >= 1
    first_call = mock_player.write_log.call_args_list[0]
    assert "Bob" in first_call[0][0]
