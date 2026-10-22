"""Tests for actions/email_control.py — email client voice tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.email_control import TOOL_SCHEMA, email_control


# ── TOOL_SCHEMA tests ──


def test_tool_schema_name():
    """TOOL_SCHEMA has the expected name."""
    assert TOOL_SCHEMA["name"] == "email_control"


def test_tool_schema_required_action():
    """TOOL_SCHEMA requires the action parameter."""
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_tool_schema_all_actions():
    """TOOL_SCHEMA description mentions all supported actions."""
    desc = TOOL_SCHEMA["description"]
    for keyword in ("configure", "send emails", "read inbox", "unread"):
        assert keyword in desc


# ── Help action ──


def test_action_help():
    """action=help returns guidance text."""
    result = email_control(parameters={"action": "help"})
    assert "Available email actions" in result
    assert "configure" in result
    assert "send_email" in result
    assert "read_inbox" in result
    assert "unread_count" in result


# ── Configuration ──


def test_action_configure_success():
    """action=configure saves email settings."""
    params = {
        "action": "configure",
        "email": "me@example.com",
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "imap_server": "imap.example.com",
        "imap_port": 993,
        "password": "app-password-123",
    }
    with patch("actions.email_control.ec.configure") as mock_configure:
        mock_configure.return_value = "Email configured for me@example.com"
        result = email_control(parameters=params)

    assert result == "Email configured for me@example.com"
    mock_configure.assert_called_once_with(
        email_addr="me@example.com",
        smtp_server="smtp.example.com",
        smtp_port=587,
        imap_server="imap.example.com",
        imap_port=993,
        password="app-password-123",
    )


def test_action_configure_missing_params():
    """action=configure returns error when required params are missing."""
    params = {"action": "configure", "email": "me@example.com"}
    result = email_control(parameters=params)
    assert "Error" in result
    assert "missing required" in result


def test_action_configure_all_fields_missing():
    """action=configure returns error when no config params given."""
    result = email_control(parameters={"action": "configure"})
    assert "Error" in result
    assert "missing required" in result


# ── Config Status ──


def test_action_config_status_configured():
    """config_status shows the configured email."""
    with patch("actions.email_control.ec.config_status") as mock_status:
        mock_status.return_value = "Email configured: me@example.com"
        result = email_control(parameters={"action": "config_status"})

    assert "me@example.com" in result


def test_action_config_status_not_configured():
    """config_status shows unconfigured state."""
    with patch("actions.email_control.ec.config_status") as mock_status:
        mock_status.return_value = "Email not configured. Use configure action."
        result = email_control(parameters={"action": "config_status"})

    assert "not configured" in result


# ── Send Email ──


def test_action_send_email_success():
    """send_email sends via ec.send_email."""
    params = {
        "action": "send_email",
        "to": "friend@example.com",
        "subject": "Hello",
        "body": "How are you?",
    }
    with patch("actions.email_control.ec.send_email") as mock_send:
        mock_send.return_value = "Email sent to friend@example.com: Hello"
        result = email_control(parameters=params)

    assert "Email sent" in result
    mock_send.assert_called_once_with(
        to="friend@example.com",
        subject="Hello",
        body="How are you?",
    )


def test_action_send_email_missing_params():
    """send_email returns error when required params are missing."""
    params = {"action": "send_email", "to": "friend@example.com"}
    result = email_control(parameters=params)
    assert "Error" in result
    assert "missing required" in result


def test_action_send_email_subject_required():
    """send_email returns error when subject is missing."""
    params = {"action": "send_email", "to": "friend@example.com", "body": "Hi"}
    result = email_control(parameters=params)
    assert "Error" in result


def test_action_send_email_body_required():
    """send_email returns error when body is missing."""
    params = {"action": "send_email", "to": "friend@example.com", "subject": "Hi"}
    result = email_control(parameters=params)
    assert "Error" in result


def test_action_send_email_empty_to():
    """send_email handles empty recipient from core layer."""
    with patch("actions.email_control.ec.send_email") as mock_send:
        mock_send.return_value = "Error: recipient address is empty."
        result = email_control(
            parameters={
                "action": "send_email",
                "to": "",
                "subject": "Hi",
                "body": "Hello",
            }
        )

    assert "Error" in result
    assert "recipient" in result


# ── Read Inbox ──


def test_action_read_inbox_default_count():
    """read_inbox uses default count of 5."""
    with patch("actions.email_control.ec.read_inbox") as mock_read:
        mock_read.return_value = "Inbox (3 of 3):\n  From: me | Subject: Test"
        result = email_control(parameters={"action": "read_inbox"})

    assert "Inbox" in result
    mock_read.assert_called_once_with(count=5)


def test_action_read_inbox_custom_count():
    """read_inbox respects custom count."""
    with patch("actions.email_control.ec.read_inbox") as mock_read:
        mock_read.return_value = "Inbox (1 of 10):\n  From: me | Subject: Latest"
        result = email_control(parameters={"action": "read_inbox", "count": 1})

    assert "Inbox" in result
    mock_read.assert_called_once_with(count=1)


def test_action_read_inbox_no_emails():
    """read_inbox handles empty inbox."""
    with patch("actions.email_control.ec.read_inbox") as mock_read:
        mock_read.return_value = "No emails in inbox."
        result = email_control(parameters={"action": "read_inbox"})

    assert "No emails" in result


def test_action_read_inbox_not_configured():
    """read_inbox returns message when email not configured."""
    with patch("actions.email_control.ec.read_inbox") as mock_read:
        mock_read.return_value = "Email not configured."
        result = email_control(parameters={"action": "read_inbox"})

    assert "not configured" in result


def test_action_read_inbox_connection_error():
    """read_inbox handles IMAP connection errors."""
    with patch("actions.email_control.ec.read_inbox") as mock_read:
        mock_read.return_value = "Failed to read inbox: Connection refused"
        result = email_control(parameters={"action": "read_inbox"})

    assert "Failed" in result


# ── Unread Count ──


def test_action_unread_count_success():
    """unread_count returns number from core."""
    with patch("actions.email_control.ec.unread_count") as mock_unread:
        mock_unread.return_value = "You have 3 unread email(s)."
        result = email_control(parameters={"action": "unread_count"})

    assert "3 unread" in result


def test_action_unread_count_zero():
    """unread_count reports zero unread."""
    with patch("actions.email_control.ec.unread_count") as mock_unread:
        mock_unread.return_value = "You have 0 unread email(s)."
        result = email_control(parameters={"action": "unread_count"})

    assert "0 unread" in result


def test_action_unread_count_not_configured():
    """unread_count returns message when not configured."""
    with patch("actions.email_control.ec.unread_count") as mock_unread:
        mock_unread.return_value = "Email not configured."
        result = email_control(parameters={"action": "unread_count"})

    assert "not configured" in result


def test_action_unread_count_imap_error():
    """unread_count handles IMAP errors gracefully."""
    with patch("actions.email_control.ec.unread_count") as mock_unread:
        mock_unread.return_value = "Failed to check: connection error"
        result = email_control(parameters={"action": "unread_count"})

    assert "Failed" in result


# ── Unknown action ──


def test_action_unknown():
    """An unrecognized action returns a clear error message."""
    result = email_control(parameters={"action": "fly_to_moon"})
    assert "Unknown action" in result
    assert "fly_to_moon" in result


def test_action_empty_string():
    """An empty action string is handled gracefully."""
    result = email_control(parameters={"action": ""})
    assert "Unknown action" in result


def test_action_missing():
    """Completely missing action returns unknown message."""
    result = email_control(parameters={})
    assert "Unknown action" in result


# ── Player parameter passthrough ──


def test_player_passthrough():
    """player argument is accepted but not used (for compatibility)."""
    mock_player = MagicMock()
    with patch("actions.email_control.ec.config_status") as mock_status:
        mock_status.return_value = "Email configured: me@example.com"
        result = email_control(
            parameters={"action": "config_status"},
            player=mock_player,
        )

    assert "Email configured" in result
