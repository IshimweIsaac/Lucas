"""Native PC control — Linux-first (Fedora/GNOME), with clear error messages."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass

from core.platform import get_os_name


@dataclass
class CmdResult:
    ok: bool
    stdout: str
    stderr: str
    code: int


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _session_env() -> dict[str, str]:
    """Subprocess env with user session bus + display (needed for playerctl/wmctrl)."""
    env = os.environ.copy()
    uid = os.getuid()
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env.setdefault("XDG_RUNTIME_DIR", runtime)
    env.setdefault(
        "DBUS_SESSION_BUS_ADDRESS",
        f"unix:path={runtime}/bus",
    )
    if _is_wayland():
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    else:
        env.setdefault("DISPLAY", ":0")
    return env


def _run(
    cmd: list[str] | str,
    *,
    shell: bool = False,
    timeout: int = 12,
    env: dict[str, str] | None = None,
) -> CmdResult:
    try:
        p = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            env=env if env is not None else _session_env(),
        )
        return CmdResult(
            ok=p.returncode == 0,
            stdout=(p.stdout or "").strip(),
            stderr=(p.stderr or "").strip(),
            code=p.returncode,
        )
    except FileNotFoundError:
        return CmdResult(False, "", f"Command not found: {cmd}", 127)
    except subprocess.TimeoutExpired:
        return CmdResult(False, "", "Command timed out", 124)
    except Exception as e:
        return CmdResult(False, "", str(e), 1)


def _which(name: str) -> bool:
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------

def battery_status() -> dict | None:
    """Return {percent, charging, status} or None if unavailable."""
    os_name = get_os_name()
    if os_name == "linux":
        r = _run(["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"])
        if not r.ok:
            # try any battery device
            en = _run(["upower", "-e"])
            if en.ok:
                for line in en.stdout.splitlines():
                    if "battery" in line.lower():
                        r = _run(["upower", "-i", line.strip()])
                        if r.ok:
                            break
        if not r.ok:
            r = _run(
                ["cat", "/sys/class/power_supply/BAT0/capacity"],
            )
            if r.ok and r.stdout.isdigit():
                return {
                    "percent": int(r.stdout),
                    "charging": _charging_from_sysfs(),
                    "status": "unknown",
                }
            return None
        pct = None
        state = ""
        for line in r.stdout.splitlines():
            if "percentage" in line.lower():
                m = re.search(r"(\d+)", line)
                if m:
                    pct = int(m.group(1))
            if line.strip().lower().startswith("state:"):
                state = line.split(":", 1)[-1].strip().lower()
        if pct is None:
            return None
        charging = state in ("charging", "fully-charged")
        return {"percent": pct, "charging": charging, "status": state or "unknown"}

    if os_name == "darwin":
        r = _run(
            [
                "pmset",
                "-g",
                "batt",
            ],
        )
        if r.ok:
            m = re.search(r"(\d+)%", r.stdout)
            if m:
                charging = "charging" in r.stdout.lower()
                return {
                    "percent": int(m.group(1)),
                    "charging": charging,
                    "status": "charging" if charging else "discharging",
                }
    return None


def _charging_from_sysfs() -> bool:
    p = "/sys/class/power_supply/BAT0/status"
    try:
        from pathlib import Path

        s = Path(p).read_text(encoding="utf-8").strip().lower()
        return s in ("charging", "full")
    except Exception:
        return False


def battery_low(threshold: int = 20) -> bool:
    b = battery_status()
    if not b:
        return False
    return b["percent"] <= threshold and not b.get("charging", False)


# ---------------------------------------------------------------------------
# Audio (PipeWire / Pulse)
# ---------------------------------------------------------------------------

def volume_set(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    os_name = get_os_name()
    if os_name == "linux":
        if not _which("pactl"):
            return "pactl not installed. Install pulseaudio-utils / pipewire-pulse."
        r = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        return f"Volume set to {percent}%." if r.ok else f"Volume failed: {r.stderr or r.stdout}"
    if os_name == "windows":
        return "Use computer_settings on Windows for volume."
    return "Volume control not implemented for this OS."


def volume_get() -> int | None:
    if get_os_name() != "linux" or not _which("pactl"):
        return None
    r = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    if not r.ok:
        return None
    m = re.search(r"(\d+)%", r.stdout)
    return int(m.group(1)) if m else None


def volume_mute_toggle() -> str:
    if get_os_name() != "linux" or not _which("pactl"):
        return "pactl not available."
    r = _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
    return "Toggled mute." if r.ok else f"Mute failed: {r.stderr}"


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------

def brightness_set(percent: int) -> str:
    percent = max(1, min(100, int(percent)))
    if get_os_name() != "linux":
        return "Use computer_settings for brightness on this OS."

    if _which("brightnessctl"):
        r = _run(["brightnessctl", "set", f"{percent}%"])
        if r.ok:
            return f"Brightness set to {percent}%."
        return f"brightnessctl failed: {r.stderr}"

    r = _run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.SettingsDaemon.Power",
            "--object-path",
            "/org/gnome/SettingsDaemon/Power",
            "--method",
            "org.freedesktop.DBus.Properties.Set",
            "org.gnome.SettingsDaemon.Power.Screen",
            "Brightness",
            f"<int32 {percent}>",
        ],
    )
    if r.ok:
        return f"Brightness set to {percent}% (GNOME)."
    return (
        "Could not set brightness. Install brightnessctl: "
        "sudo dnf install brightnessctl — and add your user to the video group."
    )


def brightness_get() -> int | None:
    if get_os_name() != "linux":
        return None
    if _which("brightnessctl"):
        r = _run(["brightnessctl", "get"])
        info = _run(["brightnessctl", "max"])
        if r.ok and info.ok:
            try:
                cur, mx = int(r.stdout), int(info.stdout)
                if mx > 0:
                    return int(cur * 100 / mx)
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------------------
# Windows (GNOME Shell on Wayland, wmctrl on X11)
# ---------------------------------------------------------------------------

def list_windows() -> list[dict]:
    if get_os_name() != "linux":
        return []
    from core import window_list

    return window_list.list_windows()


def _focus_gnome(match: str) -> str:
    from core import gnome_shell

    title = gnome_shell.focus_title_substring(match, _session_env())
    if title:
        return f"Focused: {title[:60]}"
    return ""


def focus_window(match: str) -> str:
    """Focus window whose title contains *match* (case-insensitive)."""
    m = match.strip().lower()
    if not m:
        return "No window name provided."
    if get_os_name() != "linux":
        return "Window focus is Linux-only."

    if _is_wayland():
        msg = _focus_gnome(match)
        if msg:
            return msg
        return (
            f"No window found matching '{match}'. "
            "Open the app first (Wayland uses GNOME Shell, not wmctrl)."
        )

    if _which("wmctrl"):
        r = _run(["wmctrl", "-a", match])
        if r.ok:
            return f"Focused window matching: {match}"
        for w in list_windows():
            if m in w["title"].lower():
                r2 = _run(["wmctrl", "-ia", w["id"]])
                if r2.ok:
                    return f"Focused: {w['title'][:60]}"
        gnome_msg = _focus_gnome(match)
        if gnome_msg:
            return gnome_msg
        return f"No window found matching '{match}'. Open the app first."

    gnome_msg = _focus_gnome(match)
    if gnome_msg:
        return gnome_msg

    if _which("xdotool"):
        r = _run(["xdotool", "search", "--name", match])
        if r.ok and r.stdout:
            wid = r.stdout.splitlines()[0]
            _run(["xdotool", "windowactivate", wid])
            return f"Focused via xdotool: {match}"
    return (
        "Could not focus window. On Wayland use GNOME; on X11 install wmctrl "
        "(scripts/install_pc_tools_fedora.sh)."
    )


def close_window(match: str) -> str:
    m = match.strip().lower()
    if not m:
        return "No window name provided."
    if get_os_name() != "linux":
        return "Close window is Linux-only."

    if _is_wayland():
        from core import gnome_shell

        title = gnome_shell.close_title_substring(match, _session_env())
        if title:
            return f"Closed: {title[:60]}"
        return f"No window found to close matching '{match}'."

    for w in list_windows():
        if m in w["title"].lower() and w.get("id"):
            r = _run(["wmctrl", "-ic", w["id"]])
            if r.ok:
                return f"Closed: {w['title'][:60]}"
    from core import gnome_shell

    title = gnome_shell.close_title_substring(match, _session_env())
    if title:
        return f"Closed: {title[:60]}"
    return f"No window found to close matching '{match}'."


# ---------------------------------------------------------------------------
# Browser / media (focused window + MPRIS)
# ---------------------------------------------------------------------------

# Short name → WM_CLASS mapping for browser focus matching.
_BROWSER_CLASSES: dict[str, str] = {
    "chrome": "google-chrome",
    "chromium": "chromium-browser",
    "firefox": "firefox",
    "brave": "brave-browser",
    "edge": "msedge",
    "opera": "opera",
    "vivaldi": "vivaldi",
}


def focus_browser(browser: str = "") -> str:
    """Focus a browser window.

    Builds a priority-ordered list of names to search (specific browser
    first, then common fallbacks) and tries *focus_window* with each.
    """
    names: list[str] = []
    b = browser.strip().lower()
    if b:
        wm = _BROWSER_CLASSES.get(b)
        if wm:
            names.append(wm)
        names.append(b)
    names.extend(["Mozilla", "Firefox"])
    # Also try all known class names as a broad sweep
    seen: set[str] = set()
    for v in _BROWSER_CLASSES.values():
        if v not in seen:
            names.append(v)
            seen.add(v)
    for n in ("chrome", "chromium", "firefox", "brave", "edge"):
        if n not in seen:
            names.append(n)
            seen.add(n)

    for name in names:
        msg = focus_window(name)
        if "No window" not in msg and "Could not" not in msg:
            return msg

    return f"No window found matching '{browser or 'browser'}'. Open it first."


def _wtype_hotkey(*keys: str) -> CmdResult:
    """Send hotkey via wtype (works on Wayland when browser is focused)."""
    args: list[str] = ["wtype"]
    mods: list[str] = []
    normal: list[str] = []

    def flush_mods() -> None:
        nonlocal mods
        for mod in mods:
            args.extend(["-M", mod])
        mods = []

    for raw in keys:
        k = raw.lower()
        if k in ("ctrl", "control"):
            mods.append("ctrl")
        elif k == "shift":
            mods.append("shift")
        elif k == "alt":
            mods.append("alt")
        elif k in ("super", "meta", "win"):
            mods.append("logo")
        else:
            flush_mods()
            normal.append(raw)
    flush_mods()
    args.extend(normal)
    return _run(args)


def _hotkey(*keys: str) -> str:
    if _is_wayland() and _which("wtype"):
        r = _wtype_hotkey(*keys)
        if r.ok:
            return "ok"
    try:
        import pyautogui

        pyautogui.hotkey(*keys)
        return "ok"
    except Exception as e:
        if _which("wtype"):
            r = _wtype_hotkey(*keys)
            return "ok" if r.ok else (r.stderr or str(e))
        return str(e)


def _press_key(key: str) -> str:
    if _is_wayland() and _which("wtype"):
        r = _run(["wtype", key])
        if r.ok:
            return "ok"
    try:
        import pyautogui

        pyautogui.press(key)
        return "ok"
    except Exception as e:
        return str(e)


def browser_tab(action: str) -> str:
    """Control tab in focused browser via keyboard shortcuts.

    Works on Wayland (wtype) and X11 (pyautogui).  Attempts the keyboard
    shortcut even when *focus_browser* cannot locate the window — the
    browser may already be focused.
    """
    mapping: dict[str, tuple[str, ...]] = {
        "next": ("ctrl", "Tab"),
        "prev": ("ctrl", "shift", "Tab"),
        "close": ("ctrl", "w"),
        "new": ("ctrl", "t"),
        "reload": ("ctrl", "r"),
        "fullscreen": ("f11",),
    }
    keys = mapping.get(action)
    if not keys:
        return f"Unknown tab action: {action}"

    # Best-effort focus attempt (helps direct the shortcut to the right window)
    focus = focus_browser()
    time.sleep(0.35)

    # Send keyboard shortcut — works on Wayland (wtype) and X11 (pyautogui)
    if len(keys) == 1:
        err = _press_key(keys[0])
    else:
        err = _hotkey(*keys)

    if err == "ok":
        suffix = f" ({focus.split(':')[-1].strip()})" if "Focused" in focus else ""
        return f"Browser tab: {action}{suffix}"

    # Shortcut failed — report combined error
    hint = " On Wayland install wtype: sudo dnf install wtype."
    if "No window" in focus or "Could not" in focus:
        return f"Tab action failed: {err}. {focus}{hint}"
    return f"Tab action failed: {err}.{hint}"


def _media_keyboard_fallback(cmd: str) -> str:
    if cmd not in ("play-pause", "pause", "play"):
        return ""
    focus = focus_browser()
    if "Focused" not in focus:
        return focus
    time.sleep(0.25)
    if _is_wayland() and _which("wtype"):
        r = _run(["wtype", " "])
        if r.ok:
            return f"Media: {cmd} (space in browser)."
    err = _press_key("space")
    if err == "ok":
        return f"Media: {cmd} (space in browser)."
    return f"Media keyboard fallback failed: {err}"


def media_command(cmd: str) -> str:
    """MPRIS: play, pause, play-pause, next, previous."""
    if get_os_name() != "linux":
        return "Media control is Linux-only via playerctl."
    env = _session_env()

    if _which("playerctl"):
        attempts: list[list[str]] = [
            ["playerctl", "-a", cmd],
            ["playerctl", cmd],
        ]
        for player in ("chromium", "firefox", "brave", "google-chrome"):
            attempts.append(["playerctl", "-p", player, cmd])
        last_err = ""
        for args in attempts:
            r = _run(args, env=env)
            if r.ok:
                return f"Media: {cmd}."
            last_err = r.stderr or r.stdout or "no active player"
        fb = _media_keyboard_fallback(cmd)
        if fb and "Media:" in fb:
            return fb
        return f"playerctl {cmd} failed: {last_err}. {fb or 'Focus the browser tab.'}"

    return _media_keyboard_fallback(cmd) or (
        "playerctl not installed (sudo dnf install playerctl)."
    )


def system_status_report() -> str:
    from core import system_clock as clock

    lines = ["=== PC status ===", clock.format_datetime()]
    b = battery_status()
    if b:
        ch = "charging" if b.get("charging") else "on battery"
        lines.append(f"Battery: {b['percent']}% ({ch})")
        if battery_low(20):
            lines.append("⚠️ Battery low — please plug in soon.")
    else:
        lines.append("Battery: (not detected on this machine)")

    vol = volume_get()
    if vol is not None:
        lines.append(f"Volume: {vol}%")
    br = brightness_get()
    if br is not None:
        lines.append(f"Brightness: {br}%")

    from core import window_list

    wins = list_windows()
    proc_only = wins and all(w.get("source") == "process" for w in wins)
    if wins:
        label = "Running apps" if proc_only else "Open windows"
        lines.append(f"{label}: {len(wins)}")
        for w in wins[:8]:
            lines.append(f"  - {w['title'][:70]}")
        if len(wins) > 8:
            lines.append(f"  … and {len(wins) - 8} more")
        note = window_list.window_list_diagnostic()
        if note and proc_only:
            lines.append(f"Note: {note}")
    else:
        lines.append("Open windows: (none detected)")
        note = window_list.window_list_diagnostic()
        if note:
            lines.append(f"Note: {note}")

    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    lines.append(f"Session: {session}")

    tools = []
    if _which("pactl"):
        tools.append("audio")
    if _which("brightnessctl"):
        tools.append("brightness")
    if window_list.gnome_eval_available():
        tools.append("gnome-windows")
    elif window_list.extension_list_available():
        tools.append("window-calls-ext")
    elif _which("wmctrl"):
        tools.append("wmctrl")
    if _which("playerctl"):
        tools.append("media")
    if _which("wtype"):
        tools.append("wtype-keys")
    lines.append("Control tools: " + (", ".join(tools) or "limited"))
    return "\n".join(lines)
