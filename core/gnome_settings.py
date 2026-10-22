"""GNOME gsettings wrapper — desktop settings, wallpaper, displays, screen recording."""

from __future__ import annotations

import subprocess
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)


def _run_gsettings(schema: str, key: str, *args: str) -> subprocess.CompletedProcess:
    """Run a gsettings command and return the CompletedProcess."""
    cmd = ["gsettings", schema, key, *args]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        logger.error("gsettings not found — is GNOME installed?")
        raise
    except subprocess.TimeoutExpired:
        logger.error("gsettings timed out for: %s %s", schema, key)
        raise


def get_setting(schema: str, key: str) -> str:
    """Get a GNOME gsetting value.

    Returns the raw value string on success, or an error description.
    """
    try:
        result = _run_gsettings("get", schema, key)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to read {schema} {key}: {err}"
        return result.stdout.strip().strip("'\"")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"Error reading {schema} {key}: {e}"


def set_setting(schema: str, key: str, value: str) -> str:
    """Set a GNOME gsetting value.

    Value should be the raw gsettings value string (e.g. "'prefer-dark'" for
    strings, 'true' / 'false' for booleans).
    """
    try:
        result = _run_gsettings("set", schema, key, value)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set {schema} {key}: {err}"
        return f"Set {schema} {key} to {value}."
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"Error setting {schema} {key}: {e}"


def list_displays() -> list[dict]:
    """List connected displays with their properties.

    Uses 'gnome-monitor-config list' if available, otherwise falls back to
    trying 'gnome-control-center display' or 'xrandr --listmonitors'.
    Returns a list of dicts with 'name', 'resolution', 'scale', etc.
    """
    displays: list[dict[str, Any]] = []
    try:
        result = subprocess.run(
            ["gnome-monitor-config", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.splitlines():
                if ":" in line and not line.startswith(" "):
                    # Parse: "DP-1: Dell S2722QC 3840x2160@60.00 '1.0'"
                    parts = line.strip().split()
                    if parts:
                        name = parts[0].rstrip(":")
                        display: dict[str, Any] = {"name": name}
                        for p in parts[1:]:
                            if "x" in p and "@" not in p:
                                res_parts = p.split("x")
                                if len(res_parts) == 2 and res_parts[0].isdigit():
                                    display["resolution"] = p
                            elif "@" in p:
                                display["resolution"] = p
                            elif p.replace(".", "").isdigit():
                                display["scale"] = p
                        displays.append(display)
            return displays
    except FileNotFoundError:
        pass
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Fallback: try xrandr
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if "Monitors:" in line:
                    continue
                # " 0: +*DP-1 3840/600x2160/340+0+0  DP-1"
                parts = line.split()
                for p in parts:
                    if "/" in p and not p.startswith("+"):
                        display = displays[-1] if displays else None
                        if display and "resolution" not in display:
                            display["resolution"] = p.split("/")[0]
                            break
                    if ":" in p or (p and p[0].isalpha() and not p.startswith("+")):
                        display = {"name": p.rstrip(":")}
                        displays.append(display)
                        break
            return displays
    except FileNotFoundError:
        pass
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Last fallback: return empty list
    return displays


def set_wallpaper(path: str) -> str:
    """Set the desktop wallpaper to the image at *path*.

    Works on GNOME via gsettings.
    """
    from pathlib import Path

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Wallpaper file not found: {path}"

    uri = p.as_uri()
    try:
        for schema_key in [
            ("org.gnome.desktop.background", "picture-uri"),
            ("org.gnome.desktop.background", "picture-uri-dark"),
        ]:
            result = subprocess.run(
                ["gsettings", "set", schema_key[0], schema_key[1], uri],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "Wallpaper set for %s %s failed: %s",
                    schema_key[0], schema_key[1], result.stderr.strip(),
                )

        return f"Wallpaper set to {path}"
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Wallpaper command timed out"


def set_dark_mode(enabled: bool) -> str:
    """Toggle GNOME dark/light mode.

    *enabled* = True → prefer-dark, False → default (light).
    """
    scheme = "'prefer-dark'" if enabled else "'default'"
    try:
        result = subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface",
             "color-scheme", scheme],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set dark mode: {err}"

        # Also set legacy gtk-theme for compatibility
        theme = "'Adwaita-dark'" if enabled else "'Adwaita'"
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface",
             "gtk-theme", theme],
            capture_output=True, text=True, timeout=10,
        )

        state = "enabled" if enabled else "disabled"
        return f"Dark mode {state}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Dark mode command timed out"


def set_night_light(enabled: bool) -> str:
    """Toggle GNOME night light (blue light filter)."""
    value = "true" if enabled else "false"
    try:
        result = subprocess.run(
            ["gsettings", "set", "org.gnome.settings-daemon.plugins.color",
             "night-light-enabled", value],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set night light: {err}"
        state = "enabled" if enabled else "disabled"
        return f"Night light {state}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Night light command timed out"


def set_accent_color(color: str) -> str:
    """Set GNOME accent color.

    Valid GNOME 45+ colors: blue, teal, green, yellow, orange, red, pink,
    purple, gray, slate. Pass the color name as-is (lowercase).
    """
    valid_colors = {
        "blue", "teal", "green", "yellow", "orange", "red",
        "pink", "purple", "gray", "slate",
    }
    color_clean = color.strip().lower()
    if color_clean not in valid_colors:
        return (
            f"Invalid accent color '{color}'. Valid: "
            f"{', '.join(sorted(valid_colors))}."
        )

    try:
        result = subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface",
             "accent-color", f"'{color_clean}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set accent color: {err}"
        return f"Accent color set to {color_clean}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Accent color command timed out"


def set_keyboard_layout(layout: str) -> str:
    """Set the active keyboard layout.

    *layout* is a layout code like 'us', 'fr', 'de', 'ru', etc.
    The layout must already be added to GNOME input sources.
    """
    layout_clean = layout.strip().lower()
    try:
        # First list current sources to verify layout exists
        sources_result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
            capture_output=True, text=True, timeout=10,
        )
        if sources_result.returncode != 0:
            return "Could not read input sources. Is GNOME running?"

        sources_str = sources_result.stdout.strip()
        if layout_clean not in sources_str.lower():
            logger.warning(
                "Layout '%s' may not be in input sources: %s",
                layout_clean, sources_str,
            )

        # Set the sources to only this layout (adds it if possible)
        result = subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.input-sources",
             "sources", f"[('xkb', '{layout_clean}')]"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set keyboard layout: {err}"
        return f"Keyboard layout set to {layout_clean}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Keyboard layout command timed out"


def set_touchpad_setting(setting: str, value: str) -> str:
    """Set a GNOME touchpad setting.

    Supported *setting* names (pass as-is): natural-scroll, tap-to-click,
    disable-while-typing, speed, edge-scrolling-enabled, two-finger-scrolling-enabled.
    *value* should be the raw gsettings value: 'true'/'false' for booleans,
    or a double string like "'0.5'" for speed.
    """
    setting_map = {
        "natural-scroll": ("org.gnome.desktop.peripherals.touchpad", "natural-scroll"),
        "natural_scroll": ("org.gnome.desktop.peripherals.touchpad", "natural-scroll"),
        "tap-to-click": ("org.gnome.desktop.peripherals.touchpad", "tap-to-click"),
        "tap_to_click": ("org.gnome.desktop.peripherals.touchpad", "tap-to-click"),
        "disable-while-typing": ("org.gnome.desktop.peripherals.touchpad", "disable-while-typing"),
        "disable_while_typing": ("org.gnome.desktop.peripherals.touchpad", "disable-while-typing"),
        "speed": ("org.gnome.desktop.peripherals.touchpad", "speed"),
        "edge-scrolling-enabled": ("org.gnome.desktop.peripherals.touchpad", "edge-scrolling-enabled"),
        "edge_scrolling_enabled": ("org.gnome.desktop.peripherals.touchpad", "edge-scrolling-enabled"),
        "two-finger-scrolling-enabled": ("org.gnome.desktop.peripherals.touchpad", "two-finger-scrolling-enabled"),
        "two_finger_scrolling_enabled": ("org.gnome.desktop.peripherals.touchpad", "two-finger-scrolling-enabled"),
    }

    setting_clean = setting.strip().lower().replace(" ", "_")
    mapped = setting_map.get(setting_clean)
    if not mapped:
        return (
            f"Unknown touchpad setting '{setting}'. Supported: "
            f"{', '.join(sorted({k.replace('_', '-') for k in setting_map}))}."
        )

    schema, key = mapped
    try:
        result = subprocess.run(
            ["gsettings", "set", schema, key, value],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set touchpad {setting}: {err}"
        return f"Touchpad {setting} set to {value}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Touchpad command timed out"


def set_font(font_type: str, font_name: str) -> str:
    """Set a GNOME desktop font.

    *font_type*: interface, monospace, document, or title.
    *font_name*: full font name with size, e.g. 'Cantarell 11'.
    """
    type_map = {
        "interface": ("org.gnome.desktop.interface", "font-name"),
        "monospace": ("org.gnome.desktop.interface", "monospace-font-name"),
        "document": ("org.gnome.desktop.interface", "document-font-name"),
        "title": ("org.gnome.desktop.wm.preferences", "titlebar-font"),
    }

    ft = font_type.strip().lower()
    mapped = type_map.get(ft)
    if not mapped:
        return (
            f"Unknown font type '{font_type}'. "
            f"Valid: {', '.join(type_map)}."
        )

    schema, key = mapped
    quoted = f"'{font_name}'"
    try:
        result = subprocess.run(
            ["gsettings", "set", schema, key, quoted],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set {font_type} font: {err}"
        return f"{font_type.capitalize()} font set to {font_name}."
    except FileNotFoundError:
        return "gsettings not found — is GNOME installed?"
    except subprocess.TimeoutExpired:
        return "Font command timed out"


def set_power_profile(profile: str) -> str:
    """Set the system power profile.

    Supported *profile* values: power-saver, balanced, performance.
    Uses GNOME power-profiles-daemon CLI.
    """
    valid = {"power-saver", "balanced", "performance"}
    p = profile.strip().lower().replace(" ", "-")
    if p not in valid:
        return (
            f"Invalid power profile '{profile}'. "
            f"Valid: {', '.join(sorted(valid))}."
        )

    try:
        result = subprocess.run(
            ["powerprofilesctl", "set", p],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Failed to set power profile: {err}"
        return f"Power profile set to {p}."
    except FileNotFoundError:
        return (
            "powerprofilesctl not found. Install power-profiles-daemon: "
            "sudo dnf install power-profiles-daemon"
        )
    except subprocess.TimeoutExpired:
        return "Power profile command timed out"


def start_screen_recording() -> str:
    """Start GNOME Shell screencast via D-Bus.

    Requires GNOME Shell Screen Recording D-Bus interface on
    org.gnome.Mutter.ScreenCast or org.gnome.Shell.Screencast.
    """
    try:
        import dbus
    except ImportError:
        return "dbus-python not installed. Install with: pip install dbus-python"

    try:
        bus = dbus.SessionBus()
        # Try GNOME 45+ ScreenCast interface first
        try:
            proxy = bus.get_object(
                "org.gnome.Mutter.ScreenCast",
                "/org/gnome/Mutter/ScreenCast",
            )
            interface = dbus.Interface(
                proxy, "org.gnome.Mutter.ScreenCast"
            )
            interface.Start(
                dbus.Dictionary({}, signature="sv"),
            )
            return "Screen recording started via Mutter ScreenCast."
        except dbus.DBusException:
            pass

        # Fallback: older GNOME Shell Screencast
        try:
            proxy = bus.get_object(
                "org.gnome.Shell.Screencast",
                "/org/gnome/Shell/Screencast",
            )
            interface = dbus.Interface(
                proxy, "org.gnome.Shell.Screencast"
            )
            interface.ScreencastStart(
                dbus.String(""),
                dbus.Boolean(True),
                dbus.Int32(0),
                dbus.Int32(0),
                dbus.Int32(0),
                dbus.Int32(0),
                dbus.Int32(30),
            )
            return "Screen recording started via GNOME Shell."
        except dbus.DBusException:
            pass

        return (
            "Screen recording D-Bus interface not available. "
            "Is GNOME Shell running?"
        )
    except Exception as e:
        return f"Failed to start screen recording: {e}"


def stop_screen_recording() -> str:
    """Stop GNOME Shell screencast via D-Bus."""
    try:
        import dbus
    except ImportError:
        return "dbus-python not installed. Install with: pip install dbus-python"

    try:
        bus = dbus.SessionBus()

        # Try GNOME 45+ ScreenCast interface
        try:
            proxy = bus.get_object(
                "org.gnome.Mutter.ScreenCast",
                "/org/gnome/Mutter/ScreenCast",
            )
            interface = dbus.Interface(
                proxy, "org.gnome.Mutter.ScreenCast"
            )
            interface.Stop()
            return "Screen recording stopped."
        except dbus.DBusException:
            pass

        # Fallback: older GNOME Shell Screencast
        try:
            proxy = bus.get_object(
                "org.gnome.Shell.Screencast",
                "/org/gnome/Shell/Screencast",
            )
            interface = dbus.Interface(
                proxy, "org.gnome.Shell.Screencast"
            )
            interface.ScreencastStop()
            return "Screen recording stopped."
        except dbus.DBusException:
            pass

        return (
            "Screen recording stop interface not available. "
            "Is a recording in progress?"
        )
    except Exception as e:
        return f"Failed to stop screen recording: {e}"


# ---------------------------------------------------------------------------
# Media player helpers (playerctl)
# ---------------------------------------------------------------------------

def now_playing() -> str:
    """Get currently playing media info via playerctl."""
    try:
        result = subprocess.run(
            ["playerctl", "metadata", "--format",
             "{{artist}} — {{title}} ({{album}})"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"Now playing: {result.stdout.strip()}"
        # Try without album
        result = subprocess.run(
            ["playerctl", "metadata", "--format",
             "{{artist}} — {{title}}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"Now playing: {result.stdout.strip()}"
        return "No media currently playing."
    except FileNotFoundError:
        return "playerctl not found. Install with: sudo dnf install playerctl"
    except subprocess.TimeoutExpired:
        return "playerctl timed out."


def media_control(command: str) -> str:
    """Control media playback via playerctl.

    *command*: play, pause, play-pause, next, previous, stop.
    """
    try:
        result = subprocess.run(
            ["playerctl", command],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return f"Media: {command}."
        err = result.stderr.strip() or result.stdout.strip()
        return f"Media {command} failed: {err}"
    except FileNotFoundError:
        return "playerctl not found. Install with: sudo dnf install playerctl"
    except subprocess.TimeoutExpired:
        return f"playerctl {command} timed out."


def list_players() -> str:
    """List available media players via playerctl."""
    try:
        result = subprocess.run(
            ["playerctl", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            players = result.stdout.strip().splitlines()
            if players:
                return "Media players: " + ", ".join(players)
        return "No media players detected."
    except FileNotFoundError:
        return "playerctl not found."
    except subprocess.TimeoutExpired:
        return "playerctl timed out."


def send_notification(title: str, body: str, duration_sec: int = 5) -> str:
    """Send a desktop notification via notify-send (GNOME/any freedesktop)."""
    try:
        result = subprocess.run(
            ["notify-send", "-t", str(max(1000, duration_sec * 1000)),
             title, body],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return f"Notification sent: {title}"
        err = result.stderr.strip() or result.stdout.strip()
        return f"Notification failed: {err}"
    except FileNotFoundError:
        return "notify-send not found — is libnotify installed?"
    except subprocess.TimeoutExpired:
        return "notify-send timed out."
