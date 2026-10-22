"""Lucas context awareness — environment sensing, predictive suggestions, audio routing."""

from __future__ import annotations

from core import audio_routing as ar
from core import input_devices as idev
from core import notifications_history as nh
from core.context_engine import context_summary
from core.logger import get_logger
from core.predictive_engine import get_patterns, suggest_next_action

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "context_agent",
    "description": (
        "Context awareness and environment sensing — check what you are doing, "
        "get predictive suggestions, route audio between devices, manage "
        "input devices. Lucas uses this to understand your context."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "context | patterns | suggest | "
                    "list_audio_nodes | list_audio_connections | "
                    "list_apps_audio | "
                    "connect_audio | disconnect_audio | "
                    "mute_app | route_app_to_output | "
                    "list_controllers | controller_status | "
                    "list_input_devices | "
                    "send_notification | recent_notifications"
                ),
            },
            "source": {
                "type": "STRING",
                "description": "Source audio port name for connect_audio",
            },
            "target": {
                "type": "STRING",
                "description": "Target audio port name for connect_audio",
            },
            "app_name": {
                "type": "STRING",
                "description": ("Application name for mute_app or route_app_to_output"),
            },
            "sink_name": {
                "type": "STRING",
                "description": "Audio sink name for route_app_to_output",
            },
            "mute": {
                "type": "BOOLEAN",
                "description": "True to mute, False to unmute",
            },
            "title": {
                "type": "STRING",
                "description": "Notification title",
            },
            "body": {
                "type": "STRING",
                "description": "Notification body",
            },
            "urgency": {
                "type": "STRING",
                "description": "low | normal | critical",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Number of recent notifications to show",
            },
        },
        "required": ["action"],
    },
}


def context_agent(parameters: dict, player=None) -> str:
    """Execute a context awareness action."""
    action = (parameters.get("action") or "").lower().strip()

    if player:
        player.write_log(f"[ContextAgent] {action}")

    if not action:
        return "No action provided. Use action=context for current context summary."

    handler = _HANDLERS.get(action)
    if handler is None:
        return f"Unknown action: '{action}'. Use action=context for context summary."

    try:
        return handler(parameters)
    except Exception as e:
        logger.error("context_agent action '%s' failed: %s", action, e)
        return f"Action '{action}' failed: {e}"


def _handle_context(params: dict) -> str:
    """Return current context summary."""
    return context_summary()


def _handle_patterns(params: dict) -> str:
    """Return detected activity patterns."""
    return get_patterns()


def _handle_suggest(params: dict) -> str:
    """Return suggested next action based on patterns and context."""
    return suggest_next_action()


def _handle_list_audio_nodes(params: dict) -> str:
    """List all audio nodes."""
    return ar.list_audio_nodes()


def _handle_list_audio_connections(params: dict) -> str:
    """List current audio connections."""
    return ar.list_connections()


def _handle_list_apps_audio(params: dict) -> str:
    """List applications currently using audio."""
    return ar.list_applications_audio()


def _handle_connect_audio(params: dict) -> str:
    """Connect two audio nodes."""
    source = (params.get("source") or "").strip()
    target = (params.get("target") or "").strip()
    if not source or not target:
        return "Provide source= and target= port names to connect."
    return ar.connect_node(source, target)


def _handle_disconnect_audio(params: dict) -> str:
    """Disconnect two audio nodes."""
    source = (params.get("source") or "").strip()
    target = (params.get("target") or "").strip()
    if not source or not target:
        return "Provide source= and target= port names to disconnect."
    return ar.disconnect_node(source, target)


def _handle_mute_app(params: dict) -> str:
    """Mute or unmute a specific application."""
    app_name = (params.get("app_name") or "").strip()
    if not app_name:
        return "Provide app_name= for the application to mute/unmute."
    mute = params.get("mute")
    if mute is None:
        mute = True
    elif isinstance(mute, bool):
        pass  # keep as is
    elif isinstance(mute, str):
        mute = mute.lower() in ("true", "1", "yes")
    else:
        mute = bool(mute)
    return ar.mute_application(app_name, mute)


def _handle_route_app_to_output(params: dict) -> str:
    """Route an application's audio to a specific output."""
    app_name = (params.get("app_name") or "").strip()
    sink_name = (params.get("sink_name") or "").strip()
    if not app_name:
        return "Provide app_name= for the application."
    if not sink_name:
        return "Provide sink_name= for the target audio output."
    return ar.route_application_to_output(app_name, sink_name)


def _handle_list_controllers(params: dict) -> str:
    """List game controllers."""
    return idev.list_game_controllers()


def _handle_controller_status(params: dict) -> str:
    """Check controller status."""
    return idev.controller_status()


def _handle_list_input_devices(params: dict) -> str:
    """List all input devices."""
    return idev.list_input_devices()


def _handle_send_notification(params: dict) -> str:
    """Send a desktop notification."""
    title = (params.get("title") or "Lucas").strip()
    body = (params.get("body") or "").strip()
    if not body:
        return "Provide body= for the notification."
    urgency = (params.get("urgency") or "normal").strip()
    return nh.send_notification(title, body, urgency)


def _handle_recent_notifications(params: dict) -> str:
    """Show recent notification history."""
    limit = params.get("limit", 10)
    if limit is not None:
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10
    return nh.get_recent_notifications(limit)


_HANDLERS = {
    "context": _handle_context,
    "patterns": _handle_patterns,
    "suggest": _handle_suggest,
    "list_audio_nodes": _handle_list_audio_nodes,
    "list_audio_connections": _handle_list_audio_connections,
    "list_apps_audio": _handle_list_apps_audio,
    "connect_audio": _handle_connect_audio,
    "disconnect_audio": _handle_disconnect_audio,
    "mute_app": _handle_mute_app,
    "route_app_to_output": _handle_route_app_to_output,
    "list_controllers": _handle_list_controllers,
    "controller_status": _handle_controller_status,
    "list_input_devices": _handle_list_input_devices,
    "send_notification": _handle_send_notification,
    "recent_notifications": _handle_recent_notifications,
}
