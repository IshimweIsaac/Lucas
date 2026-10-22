"""Systemd user timer management for scheduled tasks.

Creates, lists, removes, and checks status of systemd --user timer units.
Each scheduled task creates a matching .service and .timer file under
~/.config/systemd/user/.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_USER_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"


def _systemctl(args: list[str], timeout: int = 15) -> tuple[bool, str, str]:
    """Run systemctl --user with given args. Returns (ok, stdout, stderr)."""
    cmd = ["systemctl", "--user"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (
            result.returncode == 0,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except FileNotFoundError:
        return False, "", "systemctl not found — is systemd installed?"
    except subprocess.TimeoutExpired:
        return False, "", f"systemctl timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"systemctl error: {e}"


def _schedule_to_timer(schedule: str) -> str:
    """Convert a friendly schedule name or cron expression to a systemd OnCalendar.

    Supports: minutely, hourly, daily, weekly, and cron-like 'min hour dom month dow'.
    """
    sched = schedule.strip().lower()
    if sched == "minutely":
        return "*-*-* *:*:00"
    if sched == "hourly":
        return "*-*-* *:00:00"
    if sched == "daily":
        return "*-*-* 00:00:00"
    if sched == "weekly":
        return "Mon *-*-* 00:00:00"
    # Try cron expression: minute hour day month weekday
    parts = schedule.strip().split()
    if len(parts) == 5:
        minute, hour, dom, month, dow = parts
        if minute == "*":
            minute = "0"
        if hour == "*":
            hour = "0"
        if dom == "*":
            dom = "*"
        if month == "*":
            month = "*"
        if dow == "*":
            dow = "*"
        return f"{month}-{dom}-* {hour}:{minute}:00"
    # Fallback to daily
    return "*-*-* 00:00:00"


def _service_content(name: str, command: str) -> str:
    """Generate the content for a systemd .service unit file."""
    escaped_cmd = command.replace('"', '\\"')
    return f"""[Unit]
Description=Lucas scheduled task: {name}

[Service]
Type=oneshot
ExecStart=/bin/bash -c "{escaped_cmd}"
StandardOutput=journal
"""


def _timer_content(name: str, schedule: str) -> str:
    """Generate the content for a systemd .timer unit file."""
    calendar = _schedule_to_timer(schedule)
    return f"""[Unit]
Description=Lucas scheduled timer: {name}

[Timer]
OnCalendar={calendar}
Persistent=false

[Install]
WantedBy=timers.target
"""


def list_scheduled_tasks() -> str:
    """List all systemd --user timers."""
    ok, stdout, stderr = _systemctl(["list-timers", "--all", "--no-pager"])
    if not ok:
        return f"Failed to list scheduled tasks: {stderr or stdout}"
    if not stdout.strip() or "0 timers listed" in stdout.lower():
        return "No scheduled tasks (systemd user timers) found."
    return f"Scheduled Tasks (systemd --user timers):\n{stdout}"


def create_scheduled_task(name: str, command: str, schedule: str) -> str:
    """Create a systemd --user timer and service unit for a scheduled command.

    Args:
        name: Unique name for the task (used as unit filename).
        command: Shell command to execute.
        schedule: 'minutely', 'hourly', 'daily', 'weekly', or cron expression.
    """
    if not name or not command or not schedule:
        return "Provide name=, command=, and schedule= for the scheduled task."

    # Validate name (alphanumeric, hyphens, underscores only)
    clean_name = name.strip().replace(" ", "_")
    if not clean_name.isidentifier():
        return f"Invalid task name '{name}'. Use letters, digits, and underscores."

    # Ensure user systemd dir exists
    try:
        _USER_SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"Cannot create systemd user directory: {e}"

    service_path = _USER_SYSTEMD_DIR / f"{clean_name}.service"
    timer_path = _USER_SYSTEMD_DIR / f"{clean_name}.timer"

    try:
        service_path.write_text(_service_content(clean_name, command))
        timer_path.write_text(_timer_content(clean_name, schedule))
    except OSError as e:
        return f"Failed to write unit files: {e}"

    # Reload and enable
    ok, _, stderr = _systemctl(["daemon-reload"])
    if not ok:
        return f"daemon-reload failed: {stderr}"

    ok, stdout, stderr = _systemctl(["enable", "--now", f"{clean_name}.timer"])
    if not ok:
        return f"Failed to enable timer: {stderr}"

    return (
        f"Scheduled task '{clean_name}' created ({schedule}). "
        f"Timer enabled and started."
    )


def remove_scheduled_task(name: str) -> str:
    """Disable and remove a systemd --user timer and its service unit."""
    if not name:
        return "Provide name= for the scheduled task to remove."

    clean_name = name.strip().replace(" ", "_")

    # Disable and stop the timer
    ok, _, stderr = _systemctl(["disable", "--now", f"{clean_name}.timer"])
    if not ok:
        logger.warning("Failed to disable timer '%s': %s", clean_name, stderr)

    # Remove unit files
    service_path = _USER_SYSTEMD_DIR / f"{clean_name}.service"
    timer_path = _USER_SYSTEMD_DIR / f"{clean_name}.timer"
    removed = []
    for p in (service_path, timer_path):
        if p.exists():
            try:
                p.unlink()
                removed.append(p.name)
            except OSError as e:
                logger.error("Failed to remove %s: %s", p, e)

    if not removed:
        return f"No scheduled task '{clean_name}' found. Looked in {_USER_SYSTEMD_DIR}"

    ok, _, stderr = _systemctl(["daemon-reload"])
    if not ok:
        return f"daemon-reload after removal failed: {stderr}"

    return f"Scheduled task '{clean_name}' removed. Removed files: {', '.join(removed)}"


def scheduled_task_status(name: str) -> str:
    """Show the status of a systemd --user timer unit."""
    if not name:
        return "Provide name= for the scheduled task."
    clean_name = name.strip().replace(" ", "_")
    ok, stdout, stderr = _systemctl(["status", f"{clean_name}.timer", "--no-pager"])
    if not ok:
        return (
            f"Scheduled task '{clean_name}' not found: {stderr[:500] or stdout[:500]}"
        )
    return f"Status for '{clean_name}':\n{stdout}"
