"""Configure and inspect Lucas heartbeat (periodic wake-up checks)."""

from __future__ import annotations

from core import heartbeat as hb

from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "heartbeat",
    "description": (
        "Lucas heartbeat: periodic wake-ups while running to check calendar, "
        "daily routines, and upcoming events. Use status, configure, or run_now."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | configure | run_now",
            },
            "enabled": {
                "type": "BOOLEAN",
                "description": "Turn heartbeat on/off (configure)",
            },
            "interval_minutes": {
                "type": "INTEGER",
                "description": "Minutes between checks, min 5 (configure)",
            },
            "checks": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": (
                    "calendar_today | daily_routines | upcoming_events (configure)"
                ),
            },
            "custom_prompt": {
                "type": "STRING",
                "description": "Extra note included on each heartbeat (configure)",
            },
        },
        "required": ["action"],
    },
}


def heartbeat_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    cfg = hb.load_config()

    if action == "status":
        last = cfg.get("last_run_iso") or "never"
        checks = ", ".join(cfg.get("checks") or [])
        on = "on" if cfg.get("enabled", True) else "off"
        return (
            f"Heartbeat is {on}. Interval: {cfg.get('interval_minutes', 30)} min. "
            f"Checks: {checks or 'none'}. Last run: {last}."
        )

    if action == "configure":
        if "enabled" in parameters:
            cfg["enabled"] = bool(parameters["enabled"])
        if "interval_minutes" in parameters:
            cfg["interval_minutes"] = max(5, int(parameters["interval_minutes"]))
        if "checks" in parameters and parameters["checks"]:
            allowed = {"calendar_today", "daily_routines", "upcoming_events"}
            cfg["checks"] = [c for c in parameters["checks"] if c in allowed]
        if "custom_prompt" in parameters:
            cfg["custom_prompt"] = str(parameters["custom_prompt"]).strip()
        hb.save_config(cfg)
        if player:
            player.write_log("[Heartbeat] ⚙️ Configuration updated.")
        return heartbeat_control({"action": "status"}, player=player)

    if action == "run_now":
        prompt = hb.queue_wakeup(cfg)
        if not prompt:
            return "Heartbeat has nothing to check with the current settings."
        return f"Heartbeat check queued for the live session.\n{prompt[:400]}..."

    return "Unknown action. Use status, configure, or run_now."
