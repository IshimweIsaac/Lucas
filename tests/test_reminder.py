"""Tests for actions/reminder.py — timed reminder tool."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions.reminder import TOOL_SCHEMA, _get_os, _sanitise, reminder


# ---------------------------------------------------------------------------
# _sanitise
# ---------------------------------------------------------------------------


class TestSanitise:
    def test_removes_backslash(self):
        assert _sanitise("foo\\bar") == "foobar"

    def test_removes_quotes(self):
        assert _sanitise('foo"bar\'baz') == "foobarbaz"

    def test_replaces_newlines(self):
        # \n → space, \r → removed
        assert _sanitise("line1\nline2\rline3") == "line1 line2line3"

    def test_strips_whitespace(self):
        assert _sanitise("  hello  ") == "hello"

    def test_limits_length(self):
        long_str = "a" * 300
        result = _sanitise(long_str, max_len=200)
        assert len(result) == 200

    def test_empty_string(self):
        assert _sanitise("") == ""

    def test_combined(self):
        result = _sanitise(' \nhello"world\\\nfoo\r ', max_len=50)
        # \n→space, "→'', \\→'', \n→space, \r→'', strip
        assert result == "helloworld foo"


# ---------------------------------------------------------------------------
# _get_os
# ---------------------------------------------------------------------------


class TestGetOs:
    def test_reads_from_config(self, tmp_path, monkeypatch):
        """_get_os reads os_system from config/api_keys.json."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "api_keys.json"
        config_file.write_text(json.dumps({"os_system": "linux"}), encoding="utf-8")

        monkeypatch.setattr("actions.reminder.Path", lambda *a, **kw: tmp_path)
        # We need _base_dir to return tmp_path
        with patch("actions.reminder._base_dir", return_value=tmp_path):
            result = _get_os()

        assert result == "linux"

    def test_defaults_to_windows_on_error(self, monkeypatch):
        """_get_os defaults to windows when config is unreadable."""
        with patch("actions.reminder._base_dir", side_effect=Exception("broken")):
            result = _get_os()

        assert result == "windows"


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


class TestToolSchema:
    def test_tool_schema_valid(self):
        assert TOOL_SCHEMA["name"] == "reminder"
        required = TOOL_SCHEMA["parameters"]["required"]
        assert "date" in required
        assert "time" in required
        assert "message" in required


# ---------------------------------------------------------------------------
# reminder() — main function
# ---------------------------------------------------------------------------


@pytest.fixture
def future_params():
    """Return parameters with a date/time 1 hour from now."""
    future = datetime.now() + timedelta(hours=1)
    return {
        "date": future.strftime("%Y-%m-%d"),
        "time": future.strftime("%H:%M"),
        "message": "Test reminder",
    }


def _mock_completed(returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout="", stderr="")


class TestReminder:
    def test_happy_path_linux(self, future_params, tmp_path, monkeypatch):
        """A valid future date/time sets a reminder on Linux."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/systemd-run")
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: _mock_completed(returncode=0)
        )

        with patch("actions.reminder._get_os", return_value="linux"):
            result = reminder(parameters=future_params)

        assert "Reminder set for" in result
        # Verify a script file was created
        script_dir = tmp_path / ".lucas" / "reminders"
        assert script_dir.is_dir()
        scripts = list(script_dir.glob("*.py"))
        assert len(scripts) >= 1

    def test_missing_date(self):
        """Missing date returns error."""
        result = reminder(parameters={"time": "10:00", "message": "Test"})
        assert "need both a date and a time" in result

    def test_missing_time(self):
        """Missing time returns error."""
        result = reminder(parameters={"date": "2026-12-01", "message": "Test"})
        assert "need both a date and a time" in result

    def test_missing_both(self):
        """Missing both date and time returns error."""
        result = reminder(parameters={"message": "Test"})
        assert "need both a date and a time" in result

    def test_invalid_date_format(self):
        """Invalid date format returns parse error."""
        result = reminder(
            parameters={"date": "not-a-date", "time": "10:00", "message": "Test"}
        )
        assert "couldn't parse" in result.lower()

    def test_past_date_time(self):
        """A date/time in the past returns error."""
        result = reminder(
            parameters={
                "date": "2020-01-01",
                "time": "00:00",
                "message": "Way back",
            }
        )
        assert "already passed" in result or "past" in result

    def test_scheduler_fails(self, future_params, tmp_path, monkeypatch):
        """When the system scheduler fails, returns error."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/systemd-run")
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: _mock_completed(returncode=1)
        )

        with patch("actions.reminder._get_os", return_value="linux"):
            result = reminder(parameters=future_params)

        assert "couldn't register" in result or "not" in result

    def test_write_script_fails(self, future_params):
        """When writing the notify script fails, returns error."""
        with patch.object(Path, "home", side_effect=PermissionError("denied")):
            with patch("actions.reminder._get_os", return_value="linux"):
                result = reminder(parameters=future_params)

        assert "could not prepare" in result.lower()

    def test_with_player(self, future_params, tmp_path, monkeypatch):
        """reminder logs to player when provided."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/systemd-run")
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: _mock_completed(returncode=0)
        )

        mock_player = MagicMock()
        with patch("actions.reminder._get_os", return_value="linux"):
            reminder(parameters=future_params, player=mock_player)

        mock_player.write_log.assert_called_once()
        log_msg = mock_player.write_log.call_args[0][0]
        assert "Reminder" in log_msg or "✅" in log_msg

    def test_with_session_memory(self, future_params, tmp_path, monkeypatch):
        """reminder accepts session_memory parameter gracefully."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/systemd-run")
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: _mock_completed(returncode=0)
        )

        mock_memory = MagicMock()
        with patch("actions.reminder._get_os", return_value="linux"):
            result = reminder(
                parameters=future_params, session_memory=mock_memory
            )

        assert "Reminder set for" in result
