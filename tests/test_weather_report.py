"""Tests for actions/weather_report.py — weather lookup tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.weather_report import TOOL_SCHEMA, weather_action


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "weather_report"
    assert "city" in TOOL_SCHEMA["parameters"]["required"]


def test_weather_happy_path():
    """weather_action with a valid city returns a success message."""
    with patch("actions.weather_report.webbrowser.open", return_value=True):
        result = weather_action(parameters={"city": "London"})

    assert "London" in result
    assert "Showing the weather" in result


def test_weather_with_player():
    """weather_action writes a log via player when provided."""
    mock_player = MagicMock()
    with patch("actions.weather_report.webbrowser.open", return_value=True):
        result = weather_action(parameters={"city": "Nairobi"}, player=mock_player)

    assert "Nairobi" in result
    mock_player.write_log.assert_called_once()


def test_weather_with_session_memory():
    """weather_action stores search in session_memory when provided."""
    mock_memory = MagicMock()
    with patch("actions.weather_report.webbrowser.open", return_value=True):
        result = weather_action(
            parameters={"city": "Kampala"}, session_memory=mock_memory
        )

    assert "Kampala" in result
    mock_memory.set_last_search.assert_called_once()


def test_weather_missing_city():
    """weather_action without a city returns an error."""
    with patch("actions.weather_report.webbrowser.open") as mock_open:
        result = weather_action(parameters={"time": "today"})

    assert "city is missing" in result
    mock_open.assert_not_called()


def test_weather_empty_city():
    """weather_action with an empty city string returns an error."""
    with patch("actions.weather_report.webbrowser.open") as mock_open:
        result = weather_action(parameters={"city": ""})

    assert "city is missing" in result
    mock_open.assert_not_called()


def test_weather_non_string_city():
    """weather_action with a non-string city returns an error."""
    with patch("actions.weather_report.webbrowser.open") as mock_open:
        result = weather_action(parameters={"city": 123})

    assert "city is missing" in result
    mock_open.assert_not_called()


def test_weather_browser_fails():
    """weather_action handles webbrowser.open returning False."""
    with patch("actions.weather_report.webbrowser.open", return_value=False):
        result = weather_action(parameters={"city": "Paris"})

    assert "couldn't open" in result or "error" in result.lower()


def test_weather_browser_raises():
    """weather_action handles webbrowser.open raising an exception."""
    with patch(
        "actions.weather_report.webbrowser.open",
        side_effect=Exception("Browser error"),
    ):
        result = weather_action(parameters={"city": "London"})

    assert "couldn't open" in result or "Browser error" in result


def test_weather_with_time_param():
    """weather_action accepts optional time parameter."""
    with patch("actions.weather_report.webbrowser.open", return_value=True):
        result = weather_action(parameters={"city": "Tokyo", "time": "tomorrow"})

    assert "Tokyo" in result
    assert "tomorrow" in result
