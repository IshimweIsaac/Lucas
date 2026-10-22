"""Register recurring daily jobs with the OS scheduler (cron / schtasks / launchd)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.platform import get_os_name

_MARKER_PREFIX = "# LUCAS_Daily_"
_SCRIPTS_DIR = Path.home() / ".lucas" / "daily"


def _scripts_dir() -> Path:
    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    return _SCRIPTS_DIR


def _cron_dow(days: list[str]) -> str:
    idx = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
    if len(days) >= 7:
        return "*"
    return ",".join(str(idx[d]) for d in days if d in idx)


def _alert_cli_path() -> Path:
    from memory.config_manager import get_base_dir

    return get_base_dir() / "scripts" / "lucas_alert.py"


def _write_fire_script(job_id: str, message: str) -> Path:
    safe = (
        message.replace("\\", "")
        .replace('"', "")
        .replace("'", "")
        .replace("\n", " ")[:200]
    )
    msg_literal = json.dumps(safe)
    alert_py = _alert_cli_path()
    path = _scripts_dir() / f"daily_{job_id}.py"

    if alert_py.is_file():
        body = f"""# Auto-generated LUCAS daily job — do not edit
import subprocess, sys, pathlib
message = {msg_literal}
subprocess.run(
    [
        sys.executable,
        {json.dumps(str(alert_py))},
        "--message",
        message,
        "--source",
        "daily",
    ],
    check=False,
)
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    else:
        body = f"""# Auto-generated LUCAS daily job — do not edit
import json, pathlib, time, os, subprocess
message = {msg_literal}
subprocess.run(["notify-send", "LUCAS", message], check=False)
tdir = pathlib.Path.home() / ".lucas" / "triggers"
tdir.mkdir(parents=True, exist_ok=True)
p = tdir / f"trigger_{{time.time_ns()}}_{{os.getpid()}}.json"
p.write_text(json.dumps({{"message": message, "source": "daily"}}), encoding="utf-8")
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def schedule_daily(
    job_id: str,
    hour: int,
    minute: int,
    message: str,
    days: list[str],
) -> str:
    """Install or replace a daily OS job. Returns status message."""
    script = _write_fire_script(job_id, message)
    marker = f"{_MARKER_PREFIX}{job_id}"
    os_name = get_os_name()

    if os_name == "windows":
        task = f"LUCAS_Daily_{job_id}"
        subprocess.run(["schtasks", "/Delete", "/TN", task, "/F"], capture_output=True)
        # schtasks DAILY + optional /D for days — use MON,TUE,... when subset
        day_flag: list[str] = []
        if len(days) < 7:
            day_map = {d: d[:3].upper() for d in days}
            day_flag = ["/D", ",".join(day_map.values())]
        cmd = [
            "schtasks", "/Create", "/TN", task, "/TR",
            f'"{sys.executable}" "{script}"',
            "/SC", "WEEKLY" if len(days) < 7 else "DAILY",
            "/ST", f"{hour:02d}:{minute:02d}",
            "/F", *day_flag,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            cmd2 = [
                "schtasks", "/Create", "/TN", task, "/TR",
                f'"{sys.executable}" "{script}"',
                "/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}", "/F",
            ]
            result = subprocess.run(cmd2, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Windows scheduling failed: {(result.stderr or result.stdout).strip()}"
        return f"Daily reminder scheduled at {hour:02d}:{minute:02d} (task {task})."

    if os_name == "mac":
        label = f"com.lucas.daily.{job_id}"
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{sys.executable}</string><string>{script}</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
  <key>RunAtLoad</key><false/>
</dict></plist>""",
            encoding="utf-8",
        )
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        result = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
        if result.returncode != 0:
            return f"macOS scheduling failed: {result.stderr.strip()}"
        return f"Daily reminder scheduled at {hour:02d}:{minute:02d} via launchd."

    # Linux — user crontab
    cron_entry = (
        f"{minute} {hour} * * {_cron_dow(days)} "
        f"{sys.executable} {script}  {marker}"
    )
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [
            ln for ln in existing.stdout.splitlines()
            if marker not in ln and f"daily_{job_id}.py" not in ln
        ]
        lines.append(cron_entry)
        proc = subprocess.run(
            ["crontab", "-"],
            input="\n".join(lines) + "\n",
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            return f"Cron scheduling failed: {proc.stderr.strip()}"
        return f"Daily reminder scheduled at {hour:02d}:{minute:02d} via cron."
    except Exception as e:
        return f"Scheduling failed: {e}"


def cancel_routine_jobs(routine_id: str, advance_minutes: list[int] | None = None) -> None:
    """Cancel main daily job and any advance-warning jobs for a routine."""
    cancel_daily(routine_id)
    for mins in advance_minutes or (15,):
        cancel_daily(f"{routine_id}_adv{mins}")


def cancel_daily(job_id: str) -> str:
    marker = f"{_MARKER_PREFIX}{job_id}"
    os_name = get_os_name()
    script = _scripts_dir() / f"daily_{job_id}.py"

    if os_name == "windows":
        task = f"LUCAS_Daily_{job_id}"
        subprocess.run(["schtasks", "/Delete", "/TN", task, "/F"], capture_output=True)
    elif os_name == "mac":
        label = f"com.lucas.daily.{job_id}"
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if plist.exists():
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
            plist.unlink(missing_ok=True)
    else:
        try:
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            lines = [ln for ln in existing.stdout.splitlines() if marker not in ln]
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)
        except Exception:
            pass

    script.unlink(missing_ok=True)
    return "Cancelled daily OS job."
