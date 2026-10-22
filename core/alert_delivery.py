"""Desktop alerts, sounds, triggers, and optional Lucas wake."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from core.logger import get_logger
from core.platform import get_os_name
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

TRIGGER_DIR = Path.home() / ".lucas" / "triggers"
PID_FILE = Path.home() / ".lucas" / "lucas.pid"
WAKE_FLAG = Path.home() / ".lucas" / "wake_on_alert"

_KILL_GRACE_SLEEP = 0.1
_KILL_GRACE_STEPS = 30


def _repo_root() -> Path:
    return get_base_dir()


def _python() -> str:
    return sys.executable


def lucas_is_running() -> bool:
    if PID_FILE.is_file():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            try:
                PID_FILE.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        out = subprocess.run(
            ["pgrep", "-f", "main.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid_file() -> None:
    PID_FILE.unlink(missing_ok=True)


def _read_pid_file() -> int | None:
    """Return the pid stored in the pid file, or None when missing/invalid."""
    if not PID_FILE.is_file():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _candidate_pids() -> list[int]:
    """Collect live Lucas PIDs from the pid file and pgrep, excluding self."""
    pids: list[int] = []
    pid = _read_pid_file()
    if pid and pid != os.getpid():
        pids.append(pid)
    try:
        out = subprocess.run(
            ["pgrep", "-f", "main.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in (out.stdout or "").split():
            try:
                cand = int(line.strip())
            except ValueError:
                continue
            if cand and cand != os.getpid() and cand not in pids:
                pids.append(cand)
    except Exception:
        pass
    return pids


def _kill_pid(pid: int) -> bool:
    """SIGTERM, then SIGKILL after a short grace period. False if already gone."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(_KILL_GRACE_STEPS):
        time.sleep(_KILL_GRACE_SLEEP)
        try:
            os.kill(pid, 0)
        except OSError:
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


def enforce_single_instance() -> None:
    """Prevent a second Lucas instance at startup.

    If another live Lucas instance exists:
      - default: kill it (SIGTERM, SIGKILL after grace), clear the pid file,
        and continue starting as the fresh instance;
      - with LUCAS_REFUSE_SECOND=1: print a clear message and exit non-zero.
    A dead/stale pid file is already unlinked by lucas_is_running() -> just proceed.
    """
    if not lucas_is_running():
        return
    pids = _candidate_pids()
    if os.environ.get("LUCAS_REFUSE_SECOND") == "1":
        print(f"Lucas already running (PID {pids[0] if pids else 'unknown'})")
        sys.exit(1)
    logger.warning(
        "Another Lucas instance is running (PID %s). Killing it to take over.",
        ", ".join(str(p) for p in pids) or "unknown",
    )
    for pid in pids:
        _kill_pid(pid)
    clear_pid_file()


def play_alert_sound() -> bool:
    os_name = get_os_name()
    if os_name == "windows":
        try:
            import winsound

            for freq in (800, 1000, 1200):
                winsound.Beep(freq, 180)
                time.sleep(0.08)
            return True
        except Exception:
            return False

    if os_name == "mac":
        try:
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Ping.aiff"],
                check=False,
                timeout=5,
            )
            return True
        except Exception:
            pass

    candidates = [
        ["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
        ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
        ["canberra-gtk-play", "-i", "complete"],
        ["canberra-gtk-play", "-i", "message-new-instant"],
    ]
    for cmd in candidates:
        if cmd[0] and shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=False, timeout=5)
                return True
            except Exception:
                continue
    try:
        print("\a", end="", flush=True)
        return True
    except Exception:
        return False


def desktop_notify(title: str, message: str, *, urgent: bool = False) -> bool:
    os_name = get_os_name()
    if os_name == "linux" and shutil.which("notify-send"):
        args = [
            "notify-send",
            "--app-name=LUCAS",
            "--icon=dialog-information",
            f"--expire-time={'30000' if urgent else '15000'}",
        ]
        if urgent:
            args.append("--urgency=critical")
        args.extend([title, message[:240]])
        subprocess.run(args, check=False)
        return True
    if os_name == "mac":
        safe = message.replace('"', "")[:200]
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe}" with title "{title}"'],
            check=False,
        )
        return True
    try:
        from plyer import notification

        notification.notify(title=title, message=message[:240], timeout=15)
        return True
    except Exception:
        return False


def write_trigger(
    message: str,
    *,
    source: str = "alert",
    extra: dict | None = None,
) -> Path:
    TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"message": message, "source": source, "ts": time.time()}
    if extra:
        payload.update(extra)
    path = TRIGGER_DIR / f"trigger_{time.time_ns()}_{os.getpid()}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


SERVICE_NAME = "lucas.service"
_USER_UNIT = Path.home() / ".config/systemd/user" / SERVICE_NAME


def _systemd_lucas_active() -> bool:
    if not _USER_UNIT.is_file():
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (r.stdout or "").strip() == "active"
    except Exception:
        return False


def restart_lucas() -> str:
    """Relaunch Lucas immediately (systemd user service or detached main.py)."""
    if _systemd_lucas_active():
        try:
            r = subprocess.run(
                ["systemctl", "--user", "restart", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode == 0:
                return "systemd-restart"
        except Exception:
            pass

    root = _repo_root()
    main_py = root / "main.py"
    if not main_py.is_file():
        return "error: main.py not found"
    log = Path.home() / ".lucas" / "lucas_restart.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as lf:
        subprocess.Popen(
            [_python(), str(main_py)],
            cwd=str(root),
            stdout=lf,
            stderr=lf,
            start_new_session=True,
            env={**os.environ, "LUCAS_RESTART": "1"},
        )
    return "spawn-restart"


def wake_lucas_if_needed() -> str:
    """Start main.py detached when wake_on_alert is enabled and Lucas is not running."""
    if not WAKE_FLAG.exists():
        return "wake disabled"
    if lucas_is_running():
        return "already running"
    root = _repo_root()
    main_py = root / "main.py"
    if not main_py.is_file():
        return "main.py not found"
    log = Path.home() / ".lucas" / "lucas_wake.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as lf:
        subprocess.Popen(
            [_python(), str(main_py)],
            cwd=str(root),
            stdout=lf,
            stderr=lf,
            start_new_session=True,
            env={**os.environ, "LUCAS_WAKE": "1"},
        )
    return "starting lucas"


def deliver_alert(
    message: str,
    *,
    source: str = "reminder",
    sound: bool = True,
    notify: bool = True,
    trigger: bool = True,
    try_wake: bool = True,
    urgent: bool = False,
) -> dict:
    """Full alert pipeline used by cron/reminder scripts."""
    result: dict = {"message": message[:200]}
    if notify:
        result["notify"] = desktop_notify("LUCAS", message, urgent=urgent)
    if sound:
        result["sound"] = play_alert_sound()
    if trigger:
        p = write_trigger(message, source=source)
        result["trigger"] = str(p)
    if try_wake:
        result["wake"] = wake_lucas_if_needed()
    return result
