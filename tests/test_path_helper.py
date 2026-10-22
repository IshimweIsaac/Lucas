"""Tests for actions/path_helper.py — path resolution tool."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from actions.path_helper import TOOL_SCHEMA, path_helper


def test_tool_schema_name_matches_function():
    """TOOL_SCHEMA name matches the function prefix."""
    assert TOOL_SCHEMA["name"] == "path_helper"
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_known_returns_paths():
    """action=known returns registered known paths."""
    fake_paths = [
        "/home/user/Documents/Lucas",
        "/home/user/Documents/Lumina",
    ]
    with patch("actions.path_helper.known_paths", return_value=fake_paths):
        result = path_helper(parameters={"action": "known"})

    assert "Known real paths" in result
    assert "Lucas" in result
    assert "Lumina" in result


def test_known_empty_returns_message():
    """action=known with no cached paths returns a helpful message."""
    with patch("actions.path_helper.known_paths", return_value=[]):
        result = path_helper(parameters={"action": "known"})

    assert "No known paths cached yet" in result


def test_resolve_with_path_returns_resolved():
    """action=resolve with a valid path param returns the resolved path."""
    fake_res = type("Res", (), {"ok": True, "path": "/real/path", "corrected": False,
                                 "requested": "", "message": ""})()
    with patch("actions.path_helper.resolve_user_path", return_value=fake_res):
        result = path_helper(parameters={"action": "resolve", "path": "documents"})

    assert "/real/path" in result
    assert "✅" in result


def test_resolve_with_correction_shows_hint():
    """action=resolve shows corrected path hint when case was fixed."""
    fake_res = type("Res", (), {"ok": True, "path": "/real/MyProject",
                                 "corrected": True, "requested": "myproject",
                                 "message": ""})()
    with patch("actions.path_helper.resolve_user_path", return_value=fake_res):
        result = path_helper(parameters={"action": "resolve", "path": "myproject"})

    assert "/real/MyProject" in result
    assert "on-disk spelling" in result


def test_resolve_without_path_returns_error():
    """action=resolve without a path param returns an error."""
    result = path_helper(parameters={"action": "resolve"})
    assert "path is required" in result
    assert "❌" in result

    result2 = path_helper(parameters={"action": "resolve", "path": ""})
    assert "path is required" in result2


def test_resolve_failure_returns_error_message():
    """action=resolve when resolution fails returns the error."""
    fake_res = type("Res", (), {"ok": False, "path": "", "corrected": False,
                                 "requested": "", "message": "Path does not exist"})()
    with patch("actions.path_helper.resolve_user_path", return_value=fake_res):
        result = path_helper(parameters={"action": "resolve", "path": "/nonexistent"})

    assert "❌" in result
    assert "does not exist" in result


def test_unknown_action_returns_error():
    """An unrecognized action returns an error message."""
    result = path_helper(parameters={"action": "delete"})
    assert "Unknown action" in result


def test_parameters_defaults_to_empty_dict():
    """When parameters is None, function should handle gracefully."""
    result = path_helper(parameters=None)
    # Default action is "resolve" with no path
    assert "path is required" in result


@pytest.mark.parametrize("action", ["resolve", "known"])
def test_valid_actions_succeed(action):
    """Both valid actions work with appropriate mocks."""
    with patch("actions.path_helper.known_paths", return_value=["/a"]):
        with patch("actions.path_helper.resolve_user_path") as mock_res:
            mock_res.return_value = type("Res", (), {"ok": True, "path": "/a",
                                                      "corrected": False,
                                                      "requested": "",
                                                      "message": ""})()
            # Should not raise
            path_helper(parameters={"action": action})
