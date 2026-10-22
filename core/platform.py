"""OS detection for scheduling helpers."""

from __future__ import annotations

import json

from memory.config_manager import get_base_dir


def get_os_name() -> str:
    try:
        cfg = json.loads(
            (get_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "linux").lower()
    except Exception:
        import sys

        if sys.platform == "darwin":
            return "mac"
        if sys.platform.startswith("win"):
            return "windows"
        return "linux"
