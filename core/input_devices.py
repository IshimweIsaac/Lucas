"""Input device detection for Lucas — game controllers, keyboards, mice, and other input devices."""

from __future__ import annotations

from pathlib import Path

from core.logger import get_logger
from core.pc_control import _run, _which

logger = get_logger(__name__)

_INPUT_BY_ID = Path("/dev/input/by-id")


def list_input_devices() -> str:
    """List input devices connected to the system.

    Uses /dev/input/by-id/ or libinput list-devices.
    """
    lines = ["Input Devices:", ""]

    # Try /dev/input/by-id first (simplest)
    if _INPUT_BY_ID.is_dir():
        try:
            entries = sorted(
                e.name
                for e in _INPUT_BY_ID.iterdir()
                if e.is_symlink() and not e.name.startswith(".")
            )
        except OSError:
            entries = []
        if entries:
            lines.append("Via /dev/input/by-id:")
            for entry in entries:
                lines.append(f"  {entry}")
            lines.append("")
        else:
            lines.append("No input devices found in /dev/input/by-id.")
    else:
        lines.append("/dev/input/by-id not available (not running as root or no udev).")

    # Try libinput for detailed info
    if _which("libinput"):
        r = _run(["libinput", "list-devices"])
        if r.ok and r.stdout:
            lines.append("Via libinput:")
            # Parse the output to extract device names and capabilities
            for line in r.stdout.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("{"):
                    lines.append(f"  {stripped}")
            lines.append("")
        else:
            lines.append("libinput list-devices failed.")
    else:
        lines.append("libinput not available (sudo dnf install libinput-tools).")

    if len(lines) <= 2:
        return "No input devices detected."

    return "\n".join(lines)


def list_game_controllers() -> str:
    """Detect game controllers.

    Uses /dev/input/by-id/*-joystick, /dev/input/by-id/*-gamepad, and evtest.
    """
    lines = ["Game Controllers:", ""]

    # Check for joystick/gamepad entries in /dev/input/by-id
    if _INPUT_BY_ID.is_dir():
        try:
            controller_entries = [
                e.name
                for e in _INPUT_BY_ID.iterdir()
                if e.is_symlink()
                and ("joystick" in e.name.lower() or "gamepad" in e.name.lower())
            ]
        except OSError:
            controller_entries = []
        if controller_entries:
            lines.append("Via /dev/input/by-id:")
            for entry in sorted(controller_entries):
                lines.append(f"  {entry}")
            lines.append("")
        else:
            lines.append("No controllers found in /dev/input/by-id.")

    # Check /proc/bus/input/devices for gamepads/joysticks
    try:
        proc_input = Path("/proc/bus/input/devices")
        if proc_input.exists():
            text = proc_input.read_text(encoding="utf-8").lower()
            if "joystick" in text or "gamepad" in text:
                lines.append("Controller(s) detected in /proc/bus/input/devices.")
    except OSError:
        pass

    # Try evtest for available devices
    if _which("evtest"):
        r = _run(["evtest", "--grab"], timeout=3)
        if r.ok and r.stdout:
            controller_found = False
            for line in r.stdout.splitlines():
                if "joystick" in line.lower() or "gamepad" in line.lower():
                    lines.append(f"  {line.strip()}")
                    controller_found = True
            if controller_found:
                lines.append("")

    if len(lines) <= 2:
        return "No game controllers detected."

    return "\n".join(lines)


def controller_status() -> str:
    """Check if any controllers are connected and their status.

    Returns a human-readable summary of connected controllers.
    """
    lines = ["Controller Status:", ""]

    # Check via ls /dev/input
    try:
        input_dir = Path("/dev/input")
        if input_dir.is_dir():
            event_files = sorted(input_dir.glob("event*"))
            if event_files:
                lines.append(f"Found {len(event_files)} input event device(s).")
    except OSError:
        pass

    # Check via xinput (works on X11)
    if _which("xinput"):
        r = _run(["xinput", "list"])
        if r.ok and r.stdout:
            controller_found = False
            for line in r.stdout.splitlines():
                lower = line.lower()
                if any(
                    kw in lower
                    for kw in ("joystick", "gamepad", "controller", "slave  keyboard")
                ):
                    # Extract device name
                    parts = line.split()
                    if len(parts) >= 2:
                        name = parts[0].strip("⎜↳")
                        if name:
                            lines.append(f"  {name}")
                            controller_found = True
            if controller_found:
                lines.append("")

    # Check via /dev/input/by-id paths
    if _INPUT_BY_ID.is_dir():
        try:
            all_entries = list(_INPUT_BY_ID.iterdir())
            if all_entries:
                lines.append(f"Total: {len(all_entries)} input devices detected.")
                controller_entries = [
                    e.name
                    for e in all_entries
                    if e.is_symlink()
                    and ("joystick" in e.name.lower() or "gamepad" in e.name.lower())
                ]
                if controller_entries:
                    lines.append(
                        f"Game controllers: {len(controller_entries)} detected."
                    )
                    for entry in controller_entries:
                        lines.append(f"  - {entry}")
                else:
                    lines.append("No game controllers detected.")
        except OSError:
            pass

    if len(lines) <= 2:
        return "Could not determine controller status."

    return "\n".join(lines)
