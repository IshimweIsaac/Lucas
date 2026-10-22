"""Context awareness engine for Lucas — monitors user environment and provides context-aware responses."""

from __future__ import annotations

import datetime
import os
import shutil
import time

import psutil

from core.logger import get_logger
from core.pc_control import _run

logger = get_logger(__name__)

_current_context: dict = {}
_last_update: float = 0
_CONTEXT_CACHE_TTL: float = 2.0  # seconds before refresh


def _get_active_window_xdotool() -> str:
    """Get active window name using xdotool."""
    if shutil.which("xdotool"):
        r = _run(["xdotool", "getactivewindow", "getwindowname"])
        if r.ok and r.stdout:
            return r.stdout.strip()
    return ""


def _get_active_window_process() -> str:
    """Fallback: determine active app by scanning processes for GUI-like patterns."""
    user = os.environ.get("USER") or ""
    if not user:
        return ""
    r = _run(["ps", "-u", user, "-o", "pid=,comm=", "--sort=-%cpu"])
    if not r.ok:
        return ""
    stdout = r.stdout
    gui_hints = (
        "code",
        "cursor",
        "firefox",
        "chrome",
        "chromium",
        "brave",
        "nautilus",
        "gnome-terminal",
        "kitty",
        "alacritty",
        "foot",
        "konsole",
        "slack",
        "discord",
        "spotify",
        "telegram-desktop",
        "thunderbird",
        "libreoffice",
        "obs",
        "gimp",
        "inkscape",
        "steam",
        "lutris",
    )
    for line in stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        comm = parts[1].strip().split("/")[-1].lower()
        base = comm.replace("-", "").replace("_", "")
        for hint in gui_hints:
            hint_base = hint.replace("-", "").replace("_", "")
            if base == hint_base or comm == hint:
                return comm.capitalize()
    return ""


def get_context() -> dict:
    """Return current context snapshot with caching.

    Returns:
        dict with keys: active_window, active_process, time_of_day, day_of_week,
        cpu_usage, memory_usage, battery_percent, uptime, user_idle_seconds
    """
    global _current_context, _last_update
    now = time.time()
    if now - _last_update < _CONTEXT_CACHE_TTL and _current_context:
        return _current_context

    ctx: dict = {}

    # Time of day
    hour = datetime.datetime.now().hour
    if hour < 6:
        ctx["time_of_day"] = "night"
    elif hour < 12:
        ctx["time_of_day"] = "morning"
    elif hour < 17:
        ctx["time_of_day"] = "afternoon"
    elif hour < 21:
        ctx["time_of_day"] = "evening"
    else:
        ctx["time_of_day"] = "night"

    ctx["day_of_week"] = datetime.datetime.now().strftime("%A")

    # Active window
    title = _get_active_window_xdotool()
    if title:
        ctx["active_window"] = title
    ctx["active_process"] = _get_active_window_process() or "unknown"

    # System stats
    try:
        ctx["cpu_usage"] = round(psutil.cpu_percent(interval=0.1), 1)
    except Exception:
        ctx["cpu_usage"] = 0.0

    try:
        ctx["memory_usage"] = round(psutil.virtual_memory().percent, 1)
    except Exception:
        ctx["memory_usage"] = 0.0

    # Battery
    ctx["battery_percent"] = _get_battery_percent()

    # Uptime
    try:
        uptime_seconds = time.time() - psutil.boot_time()
        ctx["uptime"] = _format_uptime(uptime_seconds)
    except Exception:
        ctx["uptime"] = "unknown"

    # User idle (via xssstate or xprintidle)
    ctx["user_idle_seconds"] = _get_user_idle()

    _current_context = ctx
    _last_update = now
    return ctx


def _get_battery_percent() -> int | None:
    """Get battery percentage or None if not available."""
    try:
        if shutil.which("upower"):
            r = _run(["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"])
            if r.ok:
                for line in r.stdout.splitlines():
                    if "percentage" in line.lower():
                        m = __import__("re").search(r"(\d+)", line)
                        if m:
                            return int(m.group(1))
        bat_path = "/sys/class/power_supply/BAT0/capacity"
        if os.path.isfile(bat_path):
            with open(bat_path, encoding="utf-8") as f:
                return int(f.read().strip())
    except Exception:
        pass
    return None


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into human-readable string."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0 or not parts:
        parts.append(f"{minutes} min")
    return ", ".join(parts)


def _get_user_idle() -> int:
    """Get user idle time in seconds. Returns 0 if unavailable."""
    if shutil.which("xprintidle"):
        r = _run(["xprintidle"])
        if r.ok and r.stdout:
            try:
                return int(r.stdout.strip()) // 1000
            except ValueError:
                pass
    if shutil.which("xssstate"):
        r = _run(["xssstate", "-i"])
        if r.ok and r.stdout:
            try:
                return int(r.stdout.strip()) // 1000
            except ValueError:
                pass
    return 0


def context_summary() -> str:
    """Return a human-readable summary of current context."""
    ctx = get_context()
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")
    date_str = now.strftime("%A, %B %d")

    parts = [
        f"It's {time_str} on {date_str}.",
    ]
    if ctx.get("active_window"):
        parts.append(f"You're in {ctx['active_window']}.")
    cpu = ctx.get("cpu_usage", 0)
    mem = ctx.get("memory_usage", 0)
    parts.append(f"CPU at {cpu}%, memory at {mem}%.")
    bat = ctx.get("battery_percent")
    if bat is not None:
        parts.append(f"Battery at {bat}%.")
    uptime = ctx.get("uptime", "")
    if uptime:
        parts.append(f"System up for {uptime}.")
    idle = ctx.get("user_idle_seconds", 0)
    if idle > 60:
        parts.append(
            f"You've been idle for {idle // 60} minute{'s' if idle // 60 != 1 else ''}."
        )
    return " ".join(parts)


def is_user_active() -> bool:
    """Check if user has been active recently based on CPU and idle time."""
    ctx = get_context()
    idle = ctx.get("user_idle_seconds", 0)
    if idle > 300:  # 5 minutes idle = inactive
        return False
    cpu = ctx.get("cpu_usage", 0)
    if cpu > 5:
        return True
    return idle < 60


def detect_activity_pattern() -> str:
    """Return detected pattern: coding, browsing, meeting, gaming, idle.

    Checks active process name + CPU usage patterns.
    """
    ctx = get_context()
    process = (ctx.get("active_process") or "").lower()
    cpu = ctx.get("cpu_usage", 0)
    idle = ctx.get("user_idle_seconds", 0)

    if idle > 300:
        return "idle"

    process_lower = process.lower()
    coding_hints = (
        "code",
        "cursor",
        "vim",
        "nvim",
        "emacs",
        "neovim",
        "gnome-terminal",
        "kitty",
        "alacritty",
        "foot",
        "konsole",
        "sublime_text",
        "atom",
        "pycharm",
        "idea",
        "webstorm",
    )
    browsing_hints = (
        "firefox",
        "chrome",
        "chromium",
        "brave",
        "vivaldi",
        "edge",
        "opera",
    )
    meeting_hints = (
        "zoom",
        "teams",
        "slack",
        "discord",
        "meet",
        "skype",
        "webex",
        "google-meet",
        "telegram-desktop",
    )
    gaming_hints = (
        "steam",
        "lutris",
        "heroic",
        "wine",
        "proton",
        "gamescope",
        "amd64",
        "factorio",
        "minecraft",
        "eldenring",
    )

    for hint in coding_hints:
        if hint in process_lower:
            return "coding"
    for hint in browsing_hints:
        if hint in process_lower:
            return "browsing"
    for hint in meeting_hints:
        if hint in process_lower:
            return "meeting"
    for hint in gaming_hints:
        if hint in process_lower:
            return "gaming"

    if cpu < 10:
        return "idle"
    return "active"
