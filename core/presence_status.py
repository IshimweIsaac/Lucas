"""Presence health: process, wake, systemd, daily routines."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core import alert_delivery as ad
from core import calendar_store as cs
from memory.config_manager import get_base_dir

UNIT_PATH = Path.home() / ".config/systemd/user/lucas.service"


def snapshot() -> dict:
    data = cs.load()
    routines = data.get("daily_routines", [])
    enabled = sum(1 for r in routines if r.get("enabled", True))
    return {
        "lucas_running": ad.lucas_is_running(),
        "wake_on_alert": ad.WAKE_FLAG.is_file(),
        "systemd_installed": UNIT_PATH.is_file(),
        "systemd_active": _systemd_active(),
        "daily_routines": len(routines),
        "daily_enabled": enabled,
        "repo": str(get_base_dir()),
    }


def _systemd_active() -> bool:
    if not UNIT_PATH.is_file():
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "lucas.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def format_short() -> str:
    s = snapshot()
    parts = [
        "ON" if s["lucas_running"] else "off",
        f"wake={'Y' if s['wake_on_alert'] else 'n'}",
        f"svc={'Y' if s['systemd_active'] else 'n' if s['systemd_installed'] else '-'}",
        f"daily={s['daily_enabled']}",
    ]
    return " ".join(parts)


def format_report() -> str:
    s = snapshot()
    lines = [
        "=== Lucas presence ===",
        f"Process: {'running' if s['lucas_running'] else 'not detected'}",
        f"Wake on alert: {'enabled' if s['wake_on_alert'] else 'disabled'}",
        f"Systemd unit: {'installed' if s['systemd_installed'] else 'not installed'}",
        f"Systemd active: {'yes' if s['systemd_active'] else 'no'}",
        f"Daily routines: {s['daily_enabled']} enabled / {s['daily_routines']} total",
        f"Repo: {s['repo']}",
    ]
    if not s["wake_on_alert"]:
        lines.append("Tip: lucas_service action enable_wake")
    if not s["systemd_active"]:
        lines.append("Tip: lucas_service action install (Linux, once)")
    if s["daily_routines"] == 0:
        lines.append("Tip: calendar_manager import_reminders then sync_daily")
    return "\n".join(lines)
