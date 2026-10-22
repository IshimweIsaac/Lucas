"""List/focus windows on Linux — GNOME Wayland, extensions, X11, process fallback."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess

from core import gnome_shell


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _session_env() -> dict[str, str]:
    env = os.environ.copy()
    uid = os.getuid()
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env.setdefault("XDG_RUNTIME_DIR", runtime)
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    if _is_wayland():
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    else:
        env.setdefault("DISPLAY", ":0")
    return env


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], *, timeout: int = 12) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            env=_session_env(),
        )
        return p.returncode == 0, (p.stdout or "").strip()
    except Exception:
        return False, ""

_WINDOWS_EXT_PATH = "/org/gnome/Shell/Extensions/WindowsExt"
_WINDOWS_EXT_IFACE = "org.gnome.Shell.Extensions.WindowsExt"
_WINDOWS_PATH = "/org/gnome/Shell/Extensions/Windows"
_WINDOWS_IFACE = "org.gnome.Shell.Extensions.Windows"

# GUI processes we report when real window titles are unavailable (Wayland).
_GUI_COMM_HINTS = (
    "firefox",
    "chrome",
    "chromium",
    "brave",
    "vivaldi",
    "edge",
    "code",
    "cursor",
    "nautilus",
    "org.gnome.Nautilus",
    "vlc",
    "spotify",
    "discord",
    "slack",
    "telegram",
    "thunderbird",
    "libreoffice",
    "soffice",
    "gnome-terminal",
    "konsole",
    "kitty",
    "alacritty",
    "wezterm",
    "foot",
    "obs",
    "steam",
    "lutris",
    "gimp",
    "inkscape",
    "flameshot",
    "lucas",
    "python3",
)

_SKIP_COMM = frozenset(
    {
        "ps",
        "bash",
        "sh",
        "systemd",
        "dbus-daemon",
        "pipewire",
        "wireplumber",
        "xdg-desktop-portal",
        "gjs",
        "mutter",
        "gnome-shell",
        "Xwayland",
        "ibus-daemon",
        "sd-pam",
    }
)


def gnome_eval_available() -> bool:
    env = _session_env()
    return gnome_shell.shell_available(env)


def extension_list_available() -> bool:
    for path, iface in (
        (_WINDOWS_EXT_PATH, _WINDOWS_EXT_IFACE),
        (_WINDOWS_PATH, _WINDOWS_IFACE),
    ):
        if _gdbus_extension_list(path, iface):
            return True
    return False


def _gdbus_extension_list(
    object_path: str,
    method_iface: str,
) -> list[dict]:
    ok, stdout = _run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            object_path,
            "--method",
            f"{method_iface}.List",
            "--print-reply=literal",
        ],
    )
    if not ok or not stdout:
        return []
    return _parse_extension_list_output(stdout)


def _parse_extension_list_output(raw: str) -> list[dict]:
    """Parse gdbus literal array of window property dicts."""
    text = raw.strip()
    if not text or text in ("[]", "@as []"):
        return []
    out: list[dict] = []
    # Each window often appears as {'title': '...', 'class': '...', ...}
    for block in re.findall(r"\{[^{}]+\}", text):
        try:
            item = ast.literal_eval(block.replace("true", "True").replace("false", "False"))
        except (SyntaxError, ValueError):
            continue
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("name") or "").strip()
        if not title:
            cls = (item.get("class") or item.get("wm_class") or "").strip()
            title = cls or "Window"
        wid = str(item.get("id") or item.get("window_id") or len(out))
        pid = str(item.get("pid") or "")
        out.append({"id": wid, "pid": pid, "title": title, "source": "extension"})
    if out:
        return out
    # Fallback: extract quoted titles
    for title in re.findall(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", text):
        out.append({"id": str(len(out)), "pid": "", "title": title, "source": "extension"})
    return out


def _list_windows_wmctrl() -> list[dict]:
    if not _which("wmctrl"):
        return []
    ok, stdout = _run(["wmctrl", "-lp"])
    if not ok:
        return []
    r_stdout = stdout
    out = []
    for line in r_stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        out.append(
            {"id": parts[0], "pid": parts[2], "title": parts[4], "source": "wmctrl"}
        )
    return out


def _list_windows_gnome_eval() -> list[dict]:
    titles = gnome_shell.list_window_titles(_session_env())
    return [
        {"id": str(i), "pid": "", "title": t, "source": "gnome-eval"}
        for i, t in enumerate(titles)
    ]


def _list_windows_process() -> list[dict]:
    user = os.environ.get("USER") or ""
    if not user:
        return []
    ok, stdout = _run(["ps", "-u", user, "-o", "pid=,comm="])
    if not ok:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for line in stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        pid, comm = parts[0], parts[1].strip()
        base = comm.split("/")[-1].lower()
        if base in _SKIP_COMM or base in seen:
            continue
        if not any(h in base for h in _GUI_COMM_HINTS):
            continue
        seen.add(base)
        label = comm if comm != base else base.replace("-", " ").title()
        out.append(
            {
                "id": pid,
                "pid": pid,
                "title": f"{label} (app)",
                "source": "process",
            }
        )
    return out


def list_windows() -> list[dict]:
    """Best-effort window/app list for the current session."""
    if os.name != "posix":
        return []

    env = _session_env()

    if gnome_shell.shell_available(env):
        wins = _list_windows_gnome_eval()
        if wins:
            return wins

    for path, iface in (
        (_WINDOWS_EXT_PATH, _WINDOWS_EXT_IFACE),
        (_WINDOWS_PATH, _WINDOWS_IFACE),
    ):
        wins = _gdbus_extension_list(path, iface)
        if wins:
            return wins

    if not _is_wayland():
        wins = _list_windows_wmctrl()
        if wins:
            return wins

    # XWayland windows only on Wayland
    wins = _list_windows_wmctrl()
    if wins:
        return wins

    return _list_windows_process()


def window_list_diagnostic() -> str:
    """Short explanation when full window titles are unavailable."""
    if gnome_eval_available():
        return ""
    if _gdbus_extension_list(_WINDOWS_EXT_PATH, _WINDOWS_EXT_IFACE):
        return ""
    if _gdbus_extension_list(_WINDOWS_PATH, _WINDOWS_IFACE):
        return ""
    if _is_wayland():
        return (
            "Wayland: GNOME blocks window titles unless you install the "
            "'Window Calls Extended' shell extension "
            "(scripts/install_gnome_windows_fedora.sh), or enable GNOME unsafe mode "
            "(Alt+F2 → lg → global.context.unsafe_mode = true). "
            "Showing running apps instead."
        )
    if _which("wmctrl"):
        return "wmctrl could not list windows (check DISPLAY)."
    return "Install wmctrl (X11) or Window Calls Extended (Wayland)."

