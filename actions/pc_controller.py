"""Strong PC control: volume, brightness, windows, browser tabs, battery, media."""

from __future__ import annotations

from core import pc_control as pc
from core import system_clock as clock

from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "pc_controller",
    "description": (
        "Primary tool for controlling THIS computer: volume, brightness, battery status, "
        "focus/close apps, browser tabs (Chrome/Firefox), YouTube/media play-pause. "
        "Use instead of computer_settings for volume/brightness on Linux. "
        "After opening YouTube in browser, use browser_tab or media_toggle to control playback."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "time | date | datetime | status | volume_set | volume_up | "
                    "volume_down | mute | brightness_set | brightness_up | "
                    "brightness_down | focus_app | close_app | browser_tab | "
                    "media_play | media_pause | media_toggle | media_next | media_prev. "
                    "Use time/date/datetime for what time it is — never guess."
                ),
            },
            "value": {
                "type": "INTEGER",
                "description": "Percent 0-100 for volume_set / brightness_set",
            },
            "app": {
                "type": "STRING",
                "description": (
                    "App/window name for focus_app/close_app "
                    "(chrome, firefox, code, youtube, …)"
                ),
            },
            "tab_action": {
                "type": "STRING",
                "description": (
                    "For browser_tab: next | prev | close | new | reload | fullscreen"
                ),
            },
        },
        "required": ["action"],
    },
}


def _step_volume(delta: int) -> str:
    cur = pc.volume_get()
    if cur is None:
        return pc.volume_set(50 + delta)
    return pc.volume_set(cur + delta)


def _step_brightness(delta: int) -> str:
    cur = pc.brightness_get()
    if cur is None:
        return pc.brightness_set(50 + delta)
    return pc.brightness_set(cur + delta)


def pc_controller(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower().strip().replace(" ", "_")
    value = parameters.get("value")
    app = (parameters.get("app") or parameters.get("description") or "").strip()

    if player:
        player.write_log(f"[PC] {action}")

    if action in ("time", "current_time", "what_time"):
        return clock.format_time()

    if action in ("date", "current_date", "what_date", "today"):
        return clock.format_date()

    if action in ("datetime", "now"):
        return clock.format_datetime()

    if action == "status":
        return pc.system_status_report()

    if action in ("volume_set", "set_volume"):
        if value is None:
            return "Provide value (0-100) for volume_set."
        return pc.volume_set(int(value))

    if action == "volume_up":
        return _step_volume(10)

    if action == "volume_down":
        return _step_volume(-10)

    if action in ("mute", "toggle_mute", "unmute"):
        return pc.volume_mute_toggle()

    if action in ("brightness_set", "set_brightness"):
        if value is None:
            return "Provide value (1-100) for brightness_set."
        return pc.brightness_set(int(value))

    if action == "brightness_up":
        return _step_brightness(10)

    if action == "brightness_down":
        return _step_brightness(-10)

    if action == "focus_app":
        if not app:
            return "Provide app name (e.g. chrome, firefox, code)."
        if app.lower() in ("browser", "chrome", "youtube"):
            return pc.focus_browser(app)
        return pc.focus_window(app)

    if action == "close_app":
        if not app:
            return "Provide app name to close."
        return pc.close_window(app)

    if action == "browser_tab":
        tab = (parameters.get("tab_action") or app or "next").lower()
        return pc.browser_tab(tab)

    if action == "media_play":
        return pc.media_command("play")

    if action == "media_pause":
        return pc.media_command("pause")

    if action == "media_toggle":
        return pc.media_command("play-pause")

    if action == "media_next":
        return pc.media_command("next")

    if action == "media_prev":
        return pc.media_command("previous")

    return (
        "Unknown action. Use time, date, status, volume_set, brightness_set, "
        "focus_app, close_app, browser_tab, media_toggle, …"
    )
