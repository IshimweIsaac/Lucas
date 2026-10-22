"""Lucas background service: systemd autostart, wake-on-alert, snooze."""

from __future__ import annotations

import sys

from core import alert_delivery as ad
from core import presence_status
from core import snooze as snooze_mod
from core import systemd_service as svc

from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "lucas_service",
    "description": (
        "Background presence: install Linux autostart (systemd user), "
        "wake-on-reminder, snooze, service status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "install | uninstall | status | setup | "
                    "enable_wake | disable_wake | snooze"
                ),
            },
            "minutes": {
                "type": "INTEGER",
                "description": "Snooze minutes (action=snooze)",
            },
            "message": {
                "type": "STRING",
                "description": "Snooze reminder text",
            },
        },
        "required": ["action"],
    },
}


def lucas_service(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()

    if action == "install":
        out = svc.install()
        if player:
            player.write_log(f"[Service] {out[:80]}")
        return out

    if action == "uninstall":
        return svc.uninstall()

    if action == "status":
        return presence_status.format_report() + "\n\n" + svc.status()

    if action == "setup":
        lines = [presence_status.format_report(), ""]
        ad.WAKE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        ad.WAKE_FLAG.touch()
        lines.append("Wake on alert: enabled.")
        from actions.calendar_manager import manage_calendar

        lines.append(manage_calendar({"action": "dedupe_daily"}, player=player))
        lines.append(manage_calendar({"action": "sync_daily"}, player=player))
        if sys.platform.startswith("linux"):
            lines.append(svc.install())
        else:
            lines.append("Systemd install skipped (not Linux).")
        lines.append("")
        lines.append(presence_status.format_report())
        out = "\n".join(lines)
        if player:
            player.write_log("[Service] Presence setup complete.")
        return out

    if action == "enable_wake":
        ad.WAKE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        ad.WAKE_FLAG.touch()
        return "Wake-on-alert enabled. Reminders will start Lucas if he is not running."

    if action == "disable_wake":
        ad.WAKE_FLAG.unlink(missing_ok=True)
        return "Wake-on-alert disabled."

    if action == "snooze":
        mins = int(parameters.get("minutes", 10))
        msg = parameters.get("message", "Reminder").strip() or "Reminder"
        return snooze_mod.schedule_snooze(mins, msg)

    return (
        "Unknown action. Use install, uninstall, status, setup, "
        "enable_wake, disable_wake, or snooze."
    )
