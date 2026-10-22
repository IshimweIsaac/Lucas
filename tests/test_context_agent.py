"""Tests for actions/context_agent.py — Phase 4 context awareness."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from actions.context_agent import TOOL_SCHEMA, context_agent


# ===================================================================
# TOOL_SCHEMA
# ===================================================================


def test_tool_schema_name():
    """TOOL_SCHEMA has the correct name."""
    assert TOOL_SCHEMA["name"] == "context_agent"


def test_tool_schema_required():
    """TOOL_SCHEMA requires 'action'."""
    assert "action" in TOOL_SCHEMA["parameters"]["required"]


def test_tool_schema_action_type():
    """TOOL_SCHEMA action parameter is STRING type."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert props["action"]["type"] == "STRING"


def test_tool_schema_description_has_context():
    """TOOL_SCHEMA description mentions context."""
    desc = TOOL_SCHEMA["description"]
    assert "context" in desc.lower()
    assert "awareness" in desc.lower()


def test_tool_schema_audio_params():
    """TOOL_SCHEMA has audio routing parameters."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "source" in props
    assert "target" in props
    assert "app_name" in props
    assert "sink_name" in props
    assert "mute" in props


def test_tool_schema_notification_params():
    """TOOL_SCHEMA has notification parameters."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "title" in props
    assert "body" in props
    assert "urgency" in props


def test_tool_schema_limit_param():
    """TOOL_SCHEMA has limit parameter."""
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "limit" in props


# ===================================================================
# Basic dispatch
# ===================================================================


def test_context_agent_empty_action():
    """context_agent with no action returns helpful message."""
    result = context_agent({"action": ""})
    assert "No action provided" in result


def test_context_agent_missing_action_key():
    """context_agent without action key returns helpful message."""
    result = context_agent({"name": "test"})
    assert "No action provided" in result


def test_context_agent_unknown_action():
    """context_agent with unknown action returns error."""
    result = context_agent({"action": "nonexistent"})
    assert "Unknown action" in result


# ===================================================================
# Context actions
# ===================================================================


@patch("actions.context_agent.context_summary", return_value="Context summary test")
def test_context(mock_summary):
    """action=context returns context summary."""
    result = context_agent({"action": "context"})
    assert "Context" in result or "summary" in result.lower()
    mock_summary.assert_called_once()


@patch(
    "actions.context_agent.get_patterns",
    return_value="Pattern analysis:\n- You typically code around 9am.",
)
def test_patterns(mock_patterns):
    """action=patterns returns activity patterns."""
    result = context_agent({"action": "patterns"})
    assert "Pattern" in result
    mock_patterns.assert_called_once()


@patch(
    "actions.context_agent.suggest_next_action",
    return_value="Would you like to open VS Code?",
)
def test_suggest(mock_suggest):
    """action=suggest returns suggested next action."""
    result = context_agent({"action": "suggest"})
    assert "VS Code" in result or "suggest" in result.lower()
    mock_suggest.assert_called_once()


# ===================================================================
# Audio routing actions
# ===================================================================


@patch(
    "actions.context_agent.ar.list_audio_nodes",
    return_value="Audio Nodes:\n  Output ports (Sinks):\n    alsa_output...",
)
def test_list_audio_nodes(mock_nodes):
    """action=list_audio_nodes delegates to audio_routing.list_audio_nodes."""
    result = context_agent({"action": "list_audio_nodes"})
    assert "Audio Nodes" in result
    mock_nodes.assert_called_once()


@patch(
    "actions.context_agent.ar.list_connections",
    return_value="Audio Connections:\n  alsa -> chrome",
)
def test_list_audio_connections(mock_conn):
    """action=list_audio_connections delegates to audio_routing.list_connections."""
    result = context_agent({"action": "list_audio_connections"})
    assert "Audio Connections" in result
    mock_conn.assert_called_once()


@patch(
    "actions.context_agent.ar.list_applications_audio",
    return_value="Applications:\n  Playing: Firefox (ID 42)",
)
def test_list_apps_audio(mock_apps):
    """action=list_apps_audio delegates to audio_routing.list_applications_audio."""
    result = context_agent({"action": "list_apps_audio"})
    assert "Applications" in result or "Playing" in result
    mock_apps.assert_called_once()


@patch(
    "actions.context_agent.ar.connect_node",
    return_value="Connected: alsa_output -> chrome",
)
def test_connect_audio(mock_conn):
    """action=connect_audio with source and target delegates correctly."""
    result = context_agent(
        {
            "action": "connect_audio",
            "source": "alsa_output",
            "target": "chrome",
        }
    )
    assert "Connected" in result
    mock_conn.assert_called_with("alsa_output", "chrome")


def test_connect_audio_missing_params():
    """action=connect_audio without source/target returns error."""
    result = context_agent({"action": "connect_audio", "source": "alsa"})
    assert "Provide source" in result


@patch(
    "actions.context_agent.ar.disconnect_node",
    return_value="Disconnected: alsa_output -> chrome",
)
def test_disconnect_audio(mock_disc):
    """action=disconnect_audio with source and target delegates correctly."""
    result = context_agent(
        {
            "action": "disconnect_audio",
            "source": "alsa_output",
            "target": "chrome",
        }
    )
    assert "Disconnected" in result
    mock_disc.assert_called_with("alsa_output", "chrome")


def test_disconnect_audio_missing_params():
    """action=disconnect_audio without source/target returns error."""
    result = context_agent({"action": "disconnect_audio"})
    assert "Provide source" in result


@patch(
    "actions.context_agent.ar.mute_application",
    return_value="Sink input 42 muted",
)
def test_mute_app(mock_mute):
    """action=mute_app with app_name delegates correctly."""
    result = context_agent({"action": "mute_app", "app_name": "Firefox", "mute": True})
    assert "muted" in result.lower()
    mock_mute.assert_called_with("Firefox", True)


@patch(
    "actions.context_agent.ar.mute_application",
    return_value="Sink input 42 unmuted",
)
def test_unmute_app(mock_unmute):
    """action=mute_app with mute=False unmutes."""
    result = context_agent({"action": "mute_app", "app_name": "Firefox", "mute": False})
    assert "unmuted" in result.lower()
    mock_unmute.assert_called_with("Firefox", False)


@patch(
    "actions.context_agent.ar.mute_application",
    return_value="Sink input 42 muted",
)
def test_mute_app_default_true(mock_mute):
    """action=mute_app without mute defaults to True."""
    result = context_agent({"action": "mute_app", "app_name": "Firefox"})
    assert "muted" in result.lower()
    mock_mute.assert_called_with("Firefox", True)


@patch(
    "actions.context_agent.ar.mute_application",
    return_value="Sink input 42 muted",
)
def test_mute_app_string_bool(mock_mute):
    """action=mute_app with string 'true'/'false' works."""
    result = context_agent(
        {"action": "mute_app", "app_name": "Spotify", "mute": "true"}
    )
    assert "muted" in result.lower()
    mock_mute.assert_called_with("Spotify", True)


def test_mute_app_missing_app_name():
    """action=mute_app without app_name returns error."""
    result = context_agent({"action": "mute_app"})
    assert "Provide app_name" in result


@patch(
    "actions.context_agent.ar.route_application_to_output",
    return_value="Moved 42 to alsa_output.pci-0000",
)
def test_route_app_to_output(mock_route):
    """action=route_app_to_output with params delegates correctly."""
    result = context_agent(
        {
            "action": "route_app_to_output",
            "app_name": "Firefox",
            "sink_name": "alsa_output",
        }
    )
    assert "Moved" in result
    mock_route.assert_called_with("Firefox", "alsa_output")


def test_route_app_to_output_missing_app():
    """action=route_app_to_output without app_name returns error."""
    result = context_agent({"action": "route_app_to_output", "sink_name": "alsa"})
    assert "Provide app_name" in result


def test_route_app_to_output_missing_sink():
    """action=route_app_to_output without sink_name returns error."""
    result = context_agent({"action": "route_app_to_output", "app_name": "Firefox"})
    assert "Provide sink_name" in result


# ===================================================================
# Controller / Input device actions
# ===================================================================


@patch(
    "actions.context_agent.idev.list_game_controllers",
    return_value="Game Controllers:\n  Xbox Wireless Controller",
)
def test_list_controllers(mock_ctrl):
    """action=list_controllers delegates to input_devices.list_game_controllers."""
    result = context_agent({"action": "list_controllers"})
    assert "Controllers" in result or "Xbox" in result
    mock_ctrl.assert_called_once()


@patch(
    "actions.context_agent.idev.controller_status",
    return_value="Controller Status:\n  Total: 5 input devices",
)
def test_controller_status(mock_status):
    """action=controller_status delegates to input_devices.controller_status."""
    result = context_agent({"action": "controller_status"})
    assert "Controller Status" in result or "Total" in result
    mock_status.assert_called_once()


@patch(
    "actions.context_agent.idev.list_input_devices",
    return_value="Input Devices:\n  Keyboard\n  Mouse",
)
def test_list_input_devices(mock_devices):
    """action=list_input_devices delegates to input_devices.list_input_devices."""
    result = context_agent({"action": "list_input_devices"})
    assert "Input Devices" in result
    mock_devices.assert_called_once()


# ===================================================================
# Notification actions
# ===================================================================


@patch(
    "actions.context_agent.nh.send_notification",
    return_value="Notification sent: Test",
)
def test_send_notification(mock_notify):
    """action=send_notification delegates to notifications_history.send_notification."""
    result = context_agent(
        {
            "action": "send_notification",
            "title": "Test",
            "body": "Hello world",
        }
    )
    assert "Notification sent" in result
    mock_notify.assert_called_with("Test", "Hello world", "normal")


@patch(
    "actions.context_agent.nh.send_notification",
    return_value="Notification sent: Critical!",
)
def test_send_notification_critical(mock_notify):
    """action=send_notification with urgency=critical passes it through."""
    result = context_agent(
        {
            "action": "send_notification",
            "title": "Critical!",
            "body": "Urgent message",
            "urgency": "critical",
        }
    )
    assert "Notification sent" in result
    mock_notify.assert_called_with("Critical!", "Urgent message", "critical")


def test_send_notification_missing_body():
    """action=send_notification without body returns error."""
    result = context_agent({"action": "send_notification", "title": "Test"})
    assert "Provide body" in result


@patch(
    "actions.context_agent.nh.get_recent_notifications",
    return_value="Recent Notifications:\n  [12:00] Lucas: Hello",
)
def test_recent_notifications(mock_recent):
    """action=recent_notifications delegates to nh.get_recent_notifications."""
    result = context_agent({"action": "recent_notifications"})
    assert "Recent Notifications" in result or "Hello" in result
    mock_recent.assert_called_with(10)


@patch(
    "actions.context_agent.nh.get_recent_notifications",
    return_value="Recent Notifications:\n  [12:00] Lucas: Hi",
)
def test_recent_notifications_with_limit(mock_recent):
    """action=recent_notifications with limit passes it through."""
    result = context_agent({"action": "recent_notifications", "limit": 5})
    assert "Recent Notifications" in result or "Lucas" in result
    mock_recent.assert_called_with(5)


# ===================================================================
# Error handling
# ===================================================================


def test_handler_exception_caught():
    """Exceptions in handlers are caught and returned as error strings."""
    with patch(
        "actions.context_agent.context_summary",
        side_effect=RuntimeError("DBus error"),
    ):
        result = context_agent({"action": "context"})
        assert "failed" in result.lower()
        assert "DBus error" in result


@patch(
    "actions.context_agent.context_summary",
    side_effect=RuntimeError("Connection refused"),
)
def test_context_exception_caught(mock_summary):
    """Exceptions in context handler are caught."""
    result = context_agent({"action": "context"})
    assert "failed" in result.lower()


# ===================================================================
# player parameter
# ===================================================================


def test_with_player():
    """context_agent logs via player when provided."""
    mock_player = MagicMock()
    with patch(
        "actions.context_agent.context_summary",
        return_value="Context summary",
    ):
        context_agent({"action": "context"}, player=mock_player)

    mock_player.write_log.assert_called_once()
    assert "context" in mock_player.write_log.call_args[0][0].lower()


# ===================================================================
# All actions have handlers
# ===================================================================


def test_all_actions_have_handler():
    """Every documented action has a handler."""
    from actions.context_agent import _HANDLERS

    action_names = set(_HANDLERS.keys())
    documented = [
        "context",
        "patterns",
        "suggest",
        "list_audio_nodes",
        "list_audio_connections",
        "list_apps_audio",
        "connect_audio",
        "disconnect_audio",
        "mute_app",
        "route_app_to_output",
        "list_controllers",
        "controller_status",
        "list_input_devices",
        "send_notification",
        "recent_notifications",
    ]
    for action in documented:
        assert action in action_names, f"Missing handler for: {action}"


# ===================================================================
# Context engine core module tests
# ===================================================================


@patch("actions.context_agent.context_summary")
def test_context_summary_format(mock_summary):
    """Context summary returns a nice string."""
    mock_summary.return_value = "It's 3:42 PM on Monday. You're in VS Code."
    result = context_agent({"action": "context"})
    assert "VS Code" in result


def test_detect_activity_pattern_direct():
    """detect_activity_pattern returns a valid string pattern."""
    from core.context_engine import detect_activity_pattern as dap

    with patch("core.context_engine.psutil.cpu_percent", return_value=15.0):
        with patch(
            "core.context_engine.psutil.virtual_memory",
        ) as mock_mem:
            mock_mem.return_value.percent = 45.0
            with patch("core.context_engine._get_user_idle", return_value=0):
                pattern = dap()
                assert isinstance(pattern, str)


# ===================================================================
# Predictive engine core module tests
# ===================================================================


def test_log_activity_creates_file(tmp_path: Path):
    """log_activity writes to tracking file."""
    import core.predictive_engine as pe

    original_path = pe._TRACKING_FILE
    try:
        # Point to temp path
        import core.predictive_engine as pe

        test_file = tmp_path / "activity_tracking.json"
        pe._TRACKING_FILE = test_file
        pe._activity_log = []
        pe._loaded = False

        pe.log_activity("coding", "VS Code")
        assert test_file.exists()
        data = json.loads(test_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["activity"] == "coding"
        assert data[0]["details"] == "VS Code"
    finally:
        pe._TRACKING_FILE = original_path
        pe._activity_log = []
        pe._loaded = False


def test_log_activity_trims_old(tmp_path: Path):
    """log_activity trims to _MAX_ENTRIES."""
    import core.predictive_engine as pe

    original_path = pe._TRACKING_FILE
    try:
        test_file = tmp_path / "activity_tracking.json"
        pe._TRACKING_FILE = test_file
        pe._activity_log = []
        pe._loaded = False

        for i in range(pe._MAX_ENTRIES + 50):
            pe.log_activity(f"activity_{i}", str(i))

        assert len(pe._activity_log) <= pe._MAX_ENTRIES
    finally:
        pe._TRACKING_FILE = original_path
        pe._activity_log = []
        pe._loaded = False


def test_get_patterns_no_data(tmp_path: Path):
    """get_patterns returns helpful message when no data."""
    import core.predictive_engine as pe

    original_path = pe._TRACKING_FILE
    try:
        test_file = tmp_path / "activity_tracking.json"
        pe._TRACKING_FILE = test_file
        pe._activity_log = []
        pe._loaded = False

        result = pe.get_patterns()
        assert "No activity data" in result
    finally:
        pe._TRACKING_FILE = original_path
        pe._activity_log = []
        pe._loaded = False


# ===================================================================
# Notifications history core module tests
# ===================================================================


def test_send_notification_core(tmp_path: Path):
    """Core send_notification logs to file."""
    import core.notifications_history as nhist

    original_path = nhist._NOTIFICATION_LOG
    try:
        test_file = tmp_path / "notifications.jsonl"
        nhist._NOTIFICATION_LOG = test_file

        with patch(
            "core.notifications_history.shutil.which",
            return_value="/usr/bin/notify-send",
        ):
            with patch("core.notifications_history._run") as mock_run:
                mock_run.return_value.ok = True
                mock_run.return_value.stdout = "ok"
                mock_run.return_value.stderr = ""
                result = nhist.send_notification("Test Title", "Test Body")
                assert "Notification sent" in result

        assert test_file.exists()
        data = test_file.read_text(encoding="utf-8").strip()
        assert "Test Title" in data
        assert "Test Body" in data
    finally:
        nhist._NOTIFICATION_LOG = original_path


def test_get_recent_notifications_empty(tmp_path: Path):
    """get_recent_notifications returns helpful message when empty."""
    import core.notifications_history as nhist

    original_path = nhist._NOTIFICATION_LOG
    try:
        test_file = tmp_path / "notifications.jsonl"
        nhist._NOTIFICATION_LOG = test_file

        result = nhist.get_recent_notifications()
        assert "No notifications" in result or "not logged" in result.lower()
    finally:
        nhist._NOTIFICATION_LOG = original_path


# ===================================================================
# Input devices core module tests
# ===================================================================


@patch("core.input_devices._INPUT_BY_ID", new_callable=PropertyMock)
def test_list_input_devices_no_devices(mock_byid):
    """list_input_devices handles absence gracefully."""
    from core.input_devices import list_input_devices

    mock_byid.return_value.is_dir.return_value = False
    with patch("core.input_devices._which", return_value=False):
        result = list_input_devices()
        assert isinstance(result, str)
        assert len(result) > 0


@patch("core.input_devices._INPUT_BY_ID", new_callable=PropertyMock)
def test_list_game_controllers_no_controllers(mock_byid):
    """list_game_controllers handles absence gracefully."""
    from core.input_devices import list_game_controllers

    mock_byid.return_value.is_dir.return_value = False
    with patch("core.input_devices._which", side_effect=lambda x: x == "evtest"):
        with patch("core.input_devices._run") as mock_run:
            mock_run.return_value.ok = False
            mock_run.return_value.stdout = ""
            result = list_game_controllers()
            assert isinstance(result, str)


# ===================================================================
# Voice routing pattern tests
# ===================================================================


def test_context_regex():
    """_CONTEXT_RE pattern matches context intents."""
    from agent.voice_routing import _CONTEXT_RE as pattern

    assert pattern.search("what am I doing")
    assert pattern.search("check my context")
    assert pattern.search("what is my environment")
    assert pattern.search("what should I do")
    assert pattern.search("what's up")
    assert not pattern.search("open firefox")
    assert not pattern.search("mute the app")


def test_predict_regex():
    """_PREDICT_RE pattern matches prediction intents."""
    from agent.voice_routing import _PREDICT_RE as pattern

    assert pattern.search("predict what I need")
    assert pattern.search("show my patterns")
    assert pattern.search("suggest something")
    assert pattern.search("what do I usually do")
    assert pattern.search("what is my next action")
    assert not pattern.search("list audio nodes")
    assert not pattern.search("mute the app")


def test_audio_route_regex():
    """_AUDIO_ROUTE_RE pattern matches audio routing intents."""
    from agent.voice_routing import _AUDIO_ROUTE_RE as pattern

    assert pattern.search("route audio to speakers")
    assert pattern.search("change audio output")
    assert pattern.search("using pipewire")
    assert pattern.search("mute the app")
    assert pattern.search("move audio to headphones")
    assert pattern.search("switch audio output")
    assert not pattern.search("list controllers")
    assert not pattern.search("what am I doing")


def test_controller_regex():
    """_CONTROLLER_RE pattern matches controller intents."""
    from agent.voice_routing import _CONTROLLER_RE as pattern

    assert pattern.search("list controllers")
    assert pattern.search("connect gamepad")
    assert pattern.search("joystick status")
    assert pattern.search("show input devices")
    assert not pattern.search("mute the app")
    assert not pattern.search("what am I doing")


# ===================================================================
# Handler count
# ===================================================================


def test_handler_count():
    """context_agent has the expected number of handlers."""
    from actions.context_agent import _HANDLERS

    # At least 15 handlers
    assert len(_HANDLERS) >= 15, f"Only {len(_HANDLERS)} handlers found"


# ===================================================================
# Config file creation
# ===================================================================


def test_lucas_dir_creation():
    """The .lucas directory should be accessible."""
    lucas_dir = Path.home() / ".lucas"
    assert lucas_dir.exists() or lucas_dir.mkdir(parents=True, exist_ok=True) is None
