"""Tests for actions/browser_control.py — Playwright-based browser automation.

Strategy: Do NOT test async Playwright methods. Focus on pure functions,
TOOL_SCHEMA, the synchronous browser_control() dispatcher with mocked registry,
and internal helper functions that do not require a running browser.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions import browser_control as bc_mod
from actions.browser_control import (
    TOOL_SCHEMA,
    _BrowserSession,
    _ALIASES,
    _BROWSER_SPECS,
    _detect_default_browser,
    _firefox_profile_dir,
    _normalize_url,
    _real_profile_dir,
    _resolve_browser,
    _user_agent,
)


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_name():
    assert TOOL_SCHEMA["name"] == "browser_control"


def test_tool_schema_description():
    desc = TOOL_SCHEMA["description"]
    assert "browser" in desc
    assert "website" in desc or "web" in desc


def test_tool_schema_parameters():
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "action" in props
    assert "browser" in props
    assert "url" in props
    assert props["action"]["type"] == "STRING"
    assert props["amount"]["type"] == "INTEGER"
    assert props["incognito"]["type"] == "BOOLEAN"


def test_tool_schema_required_action():
    assert TOOL_SCHEMA["parameters"]["required"] == ["action"]


def test_tool_schema_all_property_types():
    """Every property has a valid type field."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    valid_types = {"STRING", "INTEGER", "BOOLEAN"}
    for name, prop in props.items():
        assert "type" in prop, f"Property '{name}' missing 'type'"
        assert prop["type"] in valid_types, (
            f"Property '{name}' has unexpected type '{prop['type']}'"
        )


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------


def test_normalize_url_empty():
    assert _normalize_url("") == "about:blank"
    assert _normalize_url("   ") == "about:blank"


def test_normalize_url_bare_word():
    """Bare word without dot becomes https://<word>.com"""
    assert _normalize_url("instagram") == "https://instagram.com"
    assert _normalize_url("  youtube  ") == "https://youtube.com"


def test_normalize_url_domain():
    """Domain without scheme gets https:// prepended."""
    assert _normalize_url("example.com") == "https://example.com"
    assert _normalize_url("google.co.uk") == "https://google.co.uk"


def test_normalize_url_full_url():
    """Full URL with scheme passes through unchanged."""
    assert _normalize_url("https://example.com") == "https://example.com"
    assert _normalize_url("http://localhost:8080") == "http://localhost:8080"
    assert _normalize_url("ftp://files.example.org") == "ftp://files.example.org"


# ---------------------------------------------------------------------------
# _user_agent
# ---------------------------------------------------------------------------


def test_user_agent_windows(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Windows")
    ua = _user_agent()
    assert "Windows NT" in ua
    assert "Chrome/124" in ua


def test_user_agent_darwin(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Darwin")
    ua = _user_agent()
    assert "Macintosh" in ua
    assert "Intel Mac OS X" in ua


def test_user_agent_linux(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    ua = _user_agent()
    assert "Linux x86_64" in ua
    assert "X11" in ua


def test_user_agent_unknown_os_falls_to_linux(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "FreeBSD")
    ua = _user_agent()
    assert "Linux x86_64" in ua


# ---------------------------------------------------------------------------
# _ALIASES
# ---------------------------------------------------------------------------


def test_aliases_dict():
    assert _ALIASES["google chrome"] == "chrome"
    assert _ALIASES["google-chrome"] == "chrome"
    assert _ALIASES["microsoft edge"] == "edge"
    assert _ALIASES["ms edge"] == "edge"
    assert _ALIASES["msedge"] == "edge"
    assert _ALIASES["mozilla firefox"] == "firefox"
    assert _ALIASES["opera gx"] == "operagx"
    assert _ALIASES["opera_gx"] == "operagx"


def test_aliases_not_found_returns_original():
    """Unknown browser names are not in ALIASES and should pass through."""
    assert "unknown_browser" not in _ALIASES


# ---------------------------------------------------------------------------
# _resolve_browser
# ---------------------------------------------------------------------------


def test_resolve_browser_known_returns_spec_with_engine(monkeypatch):
    """A known browser should return a dict with 'engine' key."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = _resolve_browser("chrome")
    assert spec is not None
    assert "engine" in spec
    assert spec["engine"] == "chromium"


def test_resolve_browser_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = _resolve_browser("netscape")
    assert spec is None


def test_resolve_browser_alias_resolution(monkeypatch):
    """Aliases like 'google chrome' should resolve to 'chrome' spec."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = _resolve_browser("google chrome")
    assert spec is not None
    assert spec["engine"] == "chromium"


def test_resolve_browser_safari_unsupported_on_linux(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = _resolve_browser("safari")
    assert spec is None


def test_resolve_browser_safari_supported_on_darwin(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Darwin")
    spec = _resolve_browser("safari")
    assert spec is not None
    assert spec["engine"] == "webkit"


def test_resolve_browser_windows_has_channel_for_chrome(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Windows")
    spec = _resolve_browser("chrome")
    assert spec is not None
    assert spec["channel"] == "chrome"


def test_resolve_browser_firefox_engine(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = _resolve_browser("firefox")
    assert spec is not None
    assert spec["engine"] == "firefox"


# ---------------------------------------------------------------------------
# _detect_default_browser
# ---------------------------------------------------------------------------


def test_detect_default_browser_fallback(monkeypatch):
    """On exception, fall back to 'chrome'."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")

    def _raise(*args, **kwargs):
        raise RuntimeError("mock failure")

    monkeypatch.setattr(bc_mod, "subprocess", MagicMock())
    bc_mod.subprocess.run = _raise
    assert _detect_default_browser() == "chrome"


def test_detect_default_browser_linux_chrome(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    mock_run = MagicMock()
    mock_run.return_value.stdout = "google-chrome.desktop\n"
    monkeypatch.setattr(bc_mod, "subprocess", MagicMock())
    bc_mod.subprocess.run = mock_run
    result = _detect_default_browser()
    assert result == "chrome"
    mock_run.assert_called_once_with(
        ["xdg-settings", "get", "default-web-browser"],
        capture_output=True, text=True, timeout=5,
    )


def test_detect_default_browser_linux_firefox(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    mock_run = MagicMock()
    mock_run.return_value.stdout = "firefox.desktop\n"
    monkeypatch.setattr(bc_mod, "subprocess", MagicMock())
    bc_mod.subprocess.run = mock_run
    result = _detect_default_browser()
    assert result == "firefox"


# ---------------------------------------------------------------------------
# _real_profile_dir
# ---------------------------------------------------------------------------


def test_real_profile_dir_fallback(tmp_path, monkeypatch):
    """When real profile not found, fall back to .lucas_profiles/<browser>."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = _real_profile_dir("chrome")
    assert ".lucas_profiles" in result
    assert "chrome" in result
    assert (tmp_path / ".lucas_profiles" / "chrome").exists()


def test_real_profile_dir_existing(tmp_path, monkeypatch):
    """When the real profile directory exists, return it."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    profile = tmp_path / ".config" / "google-chrome"
    profile.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = _real_profile_dir("chrome")
    assert str(profile) == result


def test_real_profile_dir_windows(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Windows")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")
    monkeypatch.setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
    result = _real_profile_dir("chrome")
    # Should fall back to .lucas_profiles since profile doesn't exist
    assert ".lucas_profiles" in result


def test_real_profile_dir_darwin(monkeypatch, tmp_path):
    monkeypatch.setattr(bc_mod, "_OS", "Darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = _real_profile_dir("chrome")
    assert ".lucas_profiles" in result


def test_real_profile_dir_unknown_browser(monkeypatch, tmp_path):
    """Unsupported browser name still returns a fallback path."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = _real_profile_dir("netscape")
    assert ".lucas_profiles" in result
    assert "netscape" in result


# ---------------------------------------------------------------------------
# _firefox_profile_dir
# ---------------------------------------------------------------------------


def test_firefox_profile_dir_missing_ini(tmp_path, monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert _firefox_profile_dir() is None


def test_firefox_profile_dir_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    mozilla = tmp_path / ".mozilla" / "firefox"
    mozilla.mkdir(parents=True)
    profile_dir = mozilla / "abcd1234.default"
    profile_dir.mkdir()
    ini = mozilla / "profiles.ini"
    ini.write_text(
        "[Profile0]\n"
        "Name=default\n"
        "Path=abcd1234.default\n"
        "Default=1\n"
        "IsRelative=1\n"
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = _firefox_profile_dir()
    assert result is not None
    assert "abcd1234.default" in result


def test_firefox_profile_dir_no_default(tmp_path, monkeypatch):
    """If no section has Default=1, return None."""
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    mozilla = tmp_path / ".mozilla" / "firefox"
    mozilla.mkdir(parents=True)
    ini = mozilla / "profiles.ini"
    ini.write_text(
        "[Profile0]\n"
        "Name=default\n"
        "Path=abcd1234.default\n"
        "Default=0\n"
        "IsRelative=1\n"
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert _firefox_profile_dir() is None


def test_firefox_profile_dir_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    mozilla = tmp_path / "Mozilla" / "Firefox"
    mozilla.mkdir(parents=True)
    profile_dir = mozilla / "xyz789.default"
    profile_dir.mkdir()
    ini = mozilla / "profiles.ini"
    ini.write_text(
        "[Profile0]\n"
        "Path=xyz789.default\n"
        "Default=1\n"
        "IsRelative=1\n"
    )
    result = _firefox_profile_dir()
    assert result is not None
    assert "xyz789.default" in result


# ---------------------------------------------------------------------------
# _BrowserSession.__init__
# ---------------------------------------------------------------------------


def test_browser_session_init_stores_name(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    monkeypatch.setattr(bc_mod, "_resolve_browser", lambda n: {"engine": "chromium"})
    session = _BrowserSession("chrome")
    assert session.browser_name == "chrome"


def test_browser_session_init_stores_resolved_spec(monkeypatch):
    monkeypatch.setattr(bc_mod, "_OS", "Linux")
    spec = {"engine": "chromium", "exe": None, "channel": None}
    monkeypatch.setattr(bc_mod, "_resolve_browser", lambda n: spec)
    session = _BrowserSession("firefox")
    assert session._spec is spec


# ---------------------------------------------------------------------------
# browser_control() — main dispatcher
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry_and_session():
    """Replace the module-level _registry with a mock, returning a mock session."""
    mock_session = MagicMock()
    mock_session.run.return_value = "mocked session result"
    with patch.object(bc_mod, "_registry") as mock_reg:
        mock_reg.get.return_value = mock_session
        mock_reg.switch.return_value = "Switched to chrome"
        mock_reg.close_all.return_value = "All browsers closed"
        mock_reg.list_sessions.return_value = "No active browser sessions."
        yield mock_reg, mock_session


def test_unknown_action(mock_registry_and_session):
    result = bc_mod.browser_control(parameters={"action": "fly_to_mars"})
    assert "Unknown browser action" in result
    assert "fly_to_mars" in result


def test_switch_action(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    result = bc_mod.browser_control(
        parameters={"action": "switch", "browser": "firefox"}
    )
    assert "Switched" in result
    mock_reg.switch.assert_called_once_with("firefox")


def test_switch_action_no_browser(mock_registry_and_session):
    """Switch without browser parameter uses 'target' fallback."""
    mock_reg, _ = mock_registry_and_session
    result = bc_mod.browser_control(
        parameters={"action": "switch", "target": "edge"}
    )
    assert "Switched" in result
    mock_reg.switch.assert_called_once_with("edge")


def test_switch_action_no_target(mock_registry_and_session):
    """Switch without any target returns 'Please specify a browser'."""
    result = bc_mod.browser_control(parameters={"action": "switch"})
    assert "specify a browser" in result


def test_list_browsers_empty(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    mock_reg.list_sessions.return_value = "No active browser sessions."
    result = bc_mod.browser_control(parameters={"action": "list_browsers"})
    assert "No active" in result


def test_list_browsers_with_sessions(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    mock_reg.list_sessions.return_value = (
        "Open browsers:\n  • chrome ◀ active\n  • firefox"
    )
    result = bc_mod.browser_control(parameters={"action": "list_browsers"})
    assert "chrome" in result
    assert "firefox" in result


def test_close_all_action(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    result = bc_mod.browser_control(parameters={"action": "close_all"})
    assert "All browsers closed" in result
    mock_reg.close_all.assert_called_once()


def test_missing_session_returns_error(mock_registry_and_session):
    """When _registry.get() raises, the error is returned as a string."""
    mock_reg, _ = mock_registry_and_session
    mock_reg.get.side_effect = RuntimeError("mock session error")
    result = bc_mod.browser_control(parameters={"action": "go_to", "url": "test.com"})
    assert "Could not start browser session" in result
    assert "mock session error" in result


def test_go_to_action(mock_registry_and_session):
    _, mock_session = mock_registry_and_session
    mock_session.run.return_value = "Opened: https://example.com"
    result = bc_mod.browser_control(
        parameters={"action": "go_to", "url": "example.com"}
    )
    assert "Opened" in result


def test_search_action(mock_registry_and_session):
    _, mock_session = mock_registry_and_session
    result = bc_mod.browser_control(
        parameters={"action": "search", "query": "pytest", "engine": "google"}
    )
    assert result is not None
    mock_session.run.assert_called_once()


def test_click_action(mock_registry_and_session):
    _, mock_session = mock_registry_and_session
    mock_session.run.return_value = "Clicked text: 'Submit'"
    result = bc_mod.browser_control(
        parameters={"action": "click", "text": "Submit"}
    )
    assert "Clicked" in result


def test_close_action_with_active_browser(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    mock_reg._active_browser = "chrome"
    mock_reg.close_one.return_value = "chrome closed."
    result = bc_mod.browser_control(parameters={"action": "close"})
    assert "chrome closed" in result


def test_close_action_no_browser(mock_registry_and_session):
    mock_reg, _ = mock_registry_and_session
    mock_reg._active_browser = ""
    result = bc_mod.browser_control(parameters={"action": "close"})
    assert "No browser specified" in result


def test_browser_control_with_player_logs(mock_registry_and_session):
    mock_player = MagicMock()
    bc_mod.browser_control(
        parameters={"action": "list_browsers"},
        player=mock_player,
    )
    mock_player.write_log.assert_called_once()


# ---------------------------------------------------------------------------
# browser_control() — timeout and error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", [
    "go_to", "search", "click", "type", "scroll", "fill_form",
    "smart_click", "smart_type", "get_text", "get_url", "press",
    "new_tab", "close_tab", "screenshot", "back", "forward", "reload",
])
def test_browser_action_dispatch_calls_run(mock_registry_and_session, action):
    """Every normal action should call sess.run() at least once."""
    _, mock_session = mock_registry_and_session
    bc_mod.browser_control(parameters={"action": action})
    assert mock_session.run.call_count >= 1, f"Action '{action}' did not call run()"


# ---------------------------------------------------------------------------
# _BROWSER_SPECS — structural integrity
# ---------------------------------------------------------------------------


def test_browser_specs_has_all_platforms():
    for plat in ("Windows", "Darwin", "Linux"):
        assert plat in _BROWSER_SPECS, f"Missing platform '{plat}'"


def test_browser_specs_known_browsers():
    """Every known browser in every supported platform has 'engine' key."""
    for plat, specs in _BROWSER_SPECS.items():
        for name, spec in specs.items():
            if spec is None:
                continue  # e.g. Safari on Linux
            assert "engine" in spec, f"{plat}/{name} missing engine"
            assert spec["engine"] in ("chromium", "firefox", "webkit")


def test_browser_specs_linux_no_safari():
    assert _BROWSER_SPECS["Linux"]["safari"] is None


def test_browser_specs_windows_safari_none():
    assert _BROWSER_SPECS["Windows"]["safari"] is None
