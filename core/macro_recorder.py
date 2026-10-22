"""Macro recording and playback — mouse and keyboard automation.

Records input events (mouse clicks, keyboard presses) and replays them.
Uses pynput when available; falls back gracefully with an informative message.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional pynput import
# ---------------------------------------------------------------------------
try:
    from pynput import keyboard, mouse

    _PYNPUT_AVAILABLE = True
except ImportError:
    _PYNPUT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MACROS_DIR = Path.home() / ".lucas" / "macros"

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_recording: bool = False
_events: list[dict] = []
_listener_thread: threading.Thread | None = None
_mouse_listener: mouse.Listener | None = None
_keyboard_listener: keyboard.Listener | None = None
_start_time: float = 0.0
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Event listeners (pynput-based)
# ---------------------------------------------------------------------------
def _on_click(x: int, y: int, button, pressed: bool) -> None:
    """Record a mouse click event."""
    with _lock:
        if not _recording:
            return
        elapsed = time.time() - _start_time
        btn_name = str(button)
        _events.append(
            {
                "type": "click",
                "time": round(elapsed, 3),
                "x": x,
                "y": y,
                "button": btn_name,
                "pressed": pressed,
            }
        )


def _on_scroll(x: int, y: int, dx: int, dy: int) -> None:
    """Record a mouse scroll event."""
    with _lock:
        if not _recording:
            return
        elapsed = time.time() - _start_time
        _events.append(
            {
                "type": "scroll",
                "time": round(elapsed, 3),
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
            }
        )


def _on_press(key) -> None:
    """Record a keyboard press event."""
    with _lock:
        if not _recording:
            return
        elapsed = time.time() - _start_time
        try:
            key_str = key.char  # type: ignore[union-attr]
        except AttributeError:
            key_str = str(key)
        _events.append(
            {
                "type": "key_press",
                "time": round(elapsed, 3),
                "key": key_str,
            }
        )


def _on_release(key) -> None:
    """Record a keyboard release event."""
    with _lock:
        if not _recording:
            return
        elapsed = time.time() - _start_time
        try:
            key_str = key.char  # type: ignore[union-attr]
        except AttributeError:
            key_str = str(key)
        _events.append(
            {
                "type": "key_release",
                "time": round(elapsed, 3),
                "key": key_str,
            }
        )
        # Stop recording on Escape press
        if key == keyboard.Key.esc:
            _stop_recording_internal()


def _start_listeners() -> str:
    """Start mouse and keyboard listeners in daemon threads."""
    global _mouse_listener, _keyboard_listener, _start_time, _events

    with _lock:
        _events = []
        _start_time = time.time()

    _mouse_listener = mouse.Listener(on_click=_on_click, on_scroll=_on_scroll)
    _keyboard_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)

    _mouse_listener.daemon = True
    _keyboard_listener.daemon = True
    _mouse_listener.start()
    _keyboard_listener.start()

    return "Recording started. Press Escape to stop recording."


def _stop_listeners() -> None:
    """Stop mouse and keyboard listeners."""
    global _mouse_listener, _keyboard_listener
    if _mouse_listener is not None:
        _mouse_listener.stop()
        _mouse_listener = None
    if _keyboard_listener is not None:
        _keyboard_listener.stop()
        _keyboard_listener = None


def _stop_recording_internal() -> None:
    """Internal helper to stop recording (thread-safe)."""
    global _recording
    with _lock:
        _recording = False
    _stop_listeners()
    logger.info("Recording stopped (%d events).", len(_events))


def _ensure_macros_dir() -> Path:
    """Create the macros directory if it doesn't exist."""
    _MACROS_DIR.mkdir(parents=True, exist_ok=True)
    return _MACROS_DIR


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_recording(path: str = "") -> str:
    """Start recording mouse and keyboard events.

    Args:
        path: Optional path to save the macro file.

    Returns:
        Confirmation message.
    """
    global _recording

    if not _PYNPUT_AVAILABLE:
        return "pynput library is not installed. Install it with: pip install pynput"

    with _lock:
        if _recording:
            return "Already recording. Press Escape to stop first."
        _recording = True

    if path:
        _ensure_macros_dir()
        # The path will be used when stopping
        pass

    return _start_listeners()


def stop_recording(path: str = "") -> str:
    """Stop recording and save events to a file.

    Args:
        path: Optional save path. Defaults to ~/.lucas/macros/macro_<timestamp>.json.

    Returns:
        Confirmation message with event count.
    """
    global _recording

    if not _PYNPUT_AVAILABLE:
        return "pynput library is not installed. Install it with: pip install pynput"

    with _lock:
        if not _recording:
            return "No recording in progress."
        _recording = False

    _stop_listeners()

    with _lock:
        events = list(_events)
        record_time = _start_time

    if not events:
        return "Recording stopped (0 events captured)."

    # Determine save path
    if path:
        save_path = Path(path).expanduser()
    else:
        timestamp = datetime.fromtimestamp(record_time).strftime("%Y%m%d_%H%M%S")
        save_path = _ensure_macros_dir() / f"macro_{timestamp}.json"

    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        macro_data = {
            "recorded": datetime.fromtimestamp(record_time).isoformat(),
            "duration": round(time.time() - record_time, 2),
            "events_count": len(events),
            "events": events,
        }
        save_path.write_text(json.dumps(macro_data, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error("Failed to save macro: %s", e)
        return f"Recording stopped but failed to save: {e}"

    return f"Recording stopped. {len(events)} events captured. Saved to: {save_path}"


def play_macro(path: str) -> str:
    """Play back a recorded macro from a JSON file.

    Currently a placeholder for pynput-based replay.
    The macro file is validated and the event count is reported.

    Args:
        path: Path to the macro JSON file.

    Returns:
        Playback status message.
    """
    if not path:
        return "Provide macro_path= to the macro file."

    if not _PYNPUT_AVAILABLE:
        return "pynput library is not installed. Install it with: pip install pynput"

    macro_path = Path(path).expanduser()
    if not macro_path.exists():
        return f"Macro file not found: {macro_path}"

    try:
        data = json.loads(macro_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return f"Failed to read macro file: {e}"

    events = data.get("events", [])
    count = len(events)
    recorded = data.get("recorded", "unknown")
    duration = data.get("duration", 0)

    if not events:
        return f"Macro '{macro_path.name}' has no events."

    # TODO: Implement actual pynput replay of mouse clicks and key presses
    return (
        f"Macro '{macro_path.name}' loaded ({count} events, "
        f"recorded {recorded}, duration {duration}s). "
        f"Playback requires full controller implementation. "
        f"Events validated and ready for playback."
    )


def recording_status() -> str:
    """Show current recording status."""
    if not _PYNPUT_AVAILABLE:
        return "pynput library not installed."
    with _lock:
        if _recording:
            elapsed = time.time() - _start_time
            return (
                f"Recording in progress ({len(_events)} events, "
                f"{elapsed:.1f}s elapsed). Press Escape to stop."
            )
        return f"Not recording. Last recording had {len(_events)} events."


def list_macros() -> str:
    """List saved macro files from the macros directory."""
    try:
        macros_dir = _ensure_macros_dir()
        files = list(macros_dir.glob("*.json"))
    except OSError as e:
        return f"Failed to list macros: {e}"

    if not files:
        return "No saved macros found."

    lines: list[str] = [f"Saved Macros ({len(files)}):"]
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        size = f.stat().st_size
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            count = data.get("events_count", "?")
        except (json.JSONDecodeError, OSError):
            count = "?"
        lines.append(f"  {f.name} ({size} bytes, {count} events, {mtime})")

    return "\n".join(lines)
