"""Tests for actions/open_app.py — application launcher tool."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from actions.open_app import TOOL_SCHEMA, _normalize, open_app


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_valid():
    """TOOL_SCHEMA has the expected structure."""
    assert TOOL_SCHEMA["name"] == "open_app"
    assert "app_name" in TOOL_SCHEMA["parameters"]["required"]
    assert TOOL_SCHEMA["parameters"]["properties"]["app_name"]["type"] == "STRING"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_missing_app_name():
    """open_app with no app_name returns an error."""
    result = open_app(parameters={})
    assert result == "No application name provided."


def test_empty_app_name():
    """open_app with empty app_name returns an error."""
    result = open_app(parameters={"app_name": ""})
    assert result == "No application name provided."


def test_none_parameters():
    """open_app with None parameters returns an error."""
    result = open_app(parameters=None)
    assert result == "No application name provided."


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize_known_alias_linux():
    """_normalize maps a known alias to the Linux binary name."""
    with patch("actions.open_app._SYSTEM", "Linux"):
        assert _normalize("chrome") == "google-chrome"
        assert _normalize("vscode") == "code"
        assert _normalize("spotify") == "spotify"


def test_normalize_known_alias_windows():
    """_normalize maps a known alias to the Windows binary name."""
    with patch("actions.open_app._SYSTEM", "Windows"):
        assert _normalize("chrome") == "chrome"
        assert _normalize("vscode") == "code"
        assert _normalize("notepad") == "notepad.exe"


def test_normalize_known_alias_macos():
    """_normalize maps a known alias to the macOS app name."""
    with patch("actions.open_app._SYSTEM", "Darwin"):
        assert _normalize("chrome") == "Google Chrome"
        assert _normalize("vscode") == "Visual Studio Code"


def test_normalize_unknown_app():
    """_normalize returns the raw name for unknown aliases."""
    assert _normalize("frobozz") == "frobozz"


def test_normalize_partial_match():
    """_normalize finds partial matches (e.g. 'google chrome')."""
    with patch("actions.open_app._SYSTEM", "Linux"):
        assert _normalize("google chrome") == "google-chrome"


def test_normalize_case_insensitive():
    """_normalize is case-insensitive."""
    with patch("actions.open_app._SYSTEM", "Linux"):
        assert _normalize("Chrome") == "google-chrome"
        assert _normalize("VSCode") == "code"


# ---------------------------------------------------------------------------
# OS dispatch
# ---------------------------------------------------------------------------


def test_unknown_os():
    """open_app with an unsupported OS returns a clear error."""
    with patch("actions.open_app._SYSTEM", "Commodore64"):
        result = open_app(parameters={"app_name": "chrome"})
        assert "Unsupported operating system" in result


# ---------------------------------------------------------------------------
# Linux launch path
# ---------------------------------------------------------------------------


def test_happy_path_linux_binary_found():
    """open_app succeeds when shutil.which finds the binary on Linux."""
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch("actions.open_app.shutil.which", return_value="/usr/bin/google-chrome"),
        patch("actions.open_app.subprocess.Popen") as mock_popen,
        patch("actions.open_app.time.sleep"),
    ):
        mock_popen.return_value = MagicMock()
        result = open_app(parameters={"app_name": "chrome"})

    assert "Opened chrome" in result
    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args
    assert call_args[0] == ["/usr/bin/google-chrome"]
    assert call_kwargs.get("stdout") is subprocess.DEVNULL
    assert call_kwargs.get("stderr") is subprocess.DEVNULL


def test_linux_binary_not_found_fallback_xdg_open():
    """open_app falls back to xdg-open when the binary is not found."""
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch("actions.open_app.shutil.which", return_value=None),
        patch("actions.open_app.subprocess.run") as mock_run,
        patch("actions.open_app.time.sleep"),
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["xdg-open", "spotify"], returncode=0, stdout="", stderr=""
        )
        result = open_app(parameters={"app_name": "spotify"})

    assert "Opened spotify" in result


def test_linux_all_launchers_fail():
    """open_app returns a failure message when all launch methods fail."""
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch("actions.open_app.shutil.which", return_value=None),
        patch(
            "actions.open_app.subprocess.run",
            side_effect=FileNotFoundError("no xdg-open"),
        ),
        patch("actions.open_app.time.sleep"),
    ):
        result = open_app(parameters={"app_name": "nonexistent_app"})

    assert "Could not confirm" in result


# ---------------------------------------------------------------------------
# Windows pyautogui fallback
# ---------------------------------------------------------------------------


def test_windows_pyautogui_fallback():
    """open_app falls back to Start Menu search via pyautogui on Windows."""
    mock_pyautogui = MagicMock()
    with (
        patch("actions.open_app._SYSTEM", "Windows"),
        patch("actions.open_app.shutil.which", return_value=None),
        patch.dict("sys.modules", {"pyautogui": mock_pyautogui}),
        patch("actions.open_app.time.sleep"),
    ):
        result = open_app(parameters={"app_name": "calculator"})

    assert "Opened calculator" in result
    mock_pyautogui.press.assert_any_call("win")
    # pyautogui.write receives the normalised name (calc.exe), not the alias
    mock_pyautogui.write.assert_called_with("calc.exe", interval=0.05)
    mock_pyautogui.press.assert_any_call("enter")


# ---------------------------------------------------------------------------
# player parameter
# ---------------------------------------------------------------------------


def test_with_player():
    """open_app writes a log via player when provided."""
    mock_player = MagicMock()
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch("actions.open_app.shutil.which", return_value="/usr/bin/google-chrome"),
        patch("actions.open_app.subprocess.Popen"),
        patch("actions.open_app.time.sleep"),
    ):
        open_app(parameters={"app_name": "chrome"}, player=mock_player)

    mock_player.write_log.assert_called_once()
    assert "chrome" in mock_player.write_log.call_args[0][0]


# ---------------------------------------------------------------------------
# Subprocess exception handling
# ---------------------------------------------------------------------------


def test_subprocess_raises_exception():
    """open_app handles subprocess.Popen raising an exception gracefully."""
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch("actions.open_app.shutil.which", return_value="/usr/bin/code"),
        patch("actions.open_app.subprocess.Popen", side_effect=OSError("exec error")),
        patch(
            "actions.open_app.subprocess.run",
            side_effect=FileNotFoundError("no fallback"),
        ),
        patch("actions.open_app.time.sleep"),
    ):
        result = open_app(parameters={"app_name": "code"})

    assert "Could not confirm" in result


# ---------------------------------------------------------------------------
# Normalise-then-launch path: alias is different from raw name
# ---------------------------------------------------------------------------


def test_alias_normalised_before_launch():
    """open_app normalises the alias and uses the normalised name for launch."""
    with (
        patch("actions.open_app._SYSTEM", "Linux"),
        patch(
            "actions.open_app.shutil.which",
            side_effect=lambda name: "/usr/bin/" + name if name == "google-chrome" else None,
        ),
        patch("actions.open_app.subprocess.Popen") as mock_popen,
        patch("actions.open_app.time.sleep"),
    ):
        mock_popen.return_value = MagicMock()
        result = open_app(parameters={"app_name": "chrome"})

    assert "Opened chrome" in result
    # The binary launched should be the normalised name, not "chrome"
    args, _ = mock_popen.call_args
    assert "google-chrome" in args[0][0]
