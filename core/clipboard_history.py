"""Clipboard history management using pyperclip.

Maintains an in-memory history of the last 20 clipboard entries.
Provides functions to get, set, list, and recall clipboard history items.
"""

from __future__ import annotations

from collections import deque

import pyperclip

from core.logger import get_logger

logger = get_logger(__name__)

_MAX_HISTORY = 20
_history: deque[str] = deque(maxlen=_MAX_HISTORY)


def clipboard_get() -> str:
    """Get current clipboard content and add it to history.

    Returns:
        The current clipboard text.
    """
    try:
        text = pyperclip.paste()
    except Exception as e:
        logger.error("clipboard_get error: %s", e)
        return f"Failed to read clipboard: {e}"

    if text:
        _add_to_history(text)
    return text if text else "Clipboard is empty."


def clipboard_copy(text: str) -> str:
    """Copy text to clipboard and add to history.

    Args:
        text: The text to copy.

    Returns:
        Confirmation message.
    """
    if not text:
        return "Provide text= to copy to clipboard."

    try:
        pyperclip.copy(text)
    except Exception as e:
        logger.error("clipboard_copy error: %s", e)
        return f"Failed to copy to clipboard: {e}"

    _add_to_history(text)
    return f"Copied to clipboard ({len(text)} chars)."


def clipboard_history() -> str:
    """Return a formatted list of clipboard history entries."""
    if not _history:
        return "Clipboard history is empty."

    lines: list[str] = [f"Clipboard History (last {len(_history)} of {_MAX_HISTORY}):"]
    for i, item in enumerate(_history):
        display = item[:80].replace("\n", "\\n")
        if len(item) > 80:
            display += "..."
        lines.append(f"  [{i}] {display}")
    return "\n".join(lines)


def clipboard_paste_history(index: int) -> str:
    """Copy a history item at the given index back to clipboard.

    Args:
        index: Zero-based index into history.

    Returns:
        Confirmation or error message.
    """
    if not _history:
        return "Clipboard history is empty."

    try:
        idx = int(index)
    except (ValueError, TypeError):
        return "Provide a valid numeric index= for clipboard history."

    if idx < 0 or idx >= len(_history):
        return (
            f"Index {idx} out of range. History has {len(_history)} "
            f"items (0-{len(_history) - 1})."
        )

    text = _history[idx]
    try:
        pyperclip.copy(text)
    except Exception as e:
        logger.error("clipboard_paste_history error: %s", e)
        return f"Failed to copy history item to clipboard: {e}"

    display = text[:60].replace("\n", "\\n")
    if len(text) > 60:
        display += "..."
    return f'History item [{idx}] copied to clipboard: "{display}"'


def clear_history() -> None:
    """Clear the clipboard history."""
    _history.clear()


def _add_to_history(text: str) -> None:
    """Add text to history, avoiding duplicates with the most recent entry."""
    if text and (not _history or _history[-1] != text):
        _history.append(text)
