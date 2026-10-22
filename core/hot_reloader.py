"""Hot-reloader — watches Lucas source files and auto-reloads changed modules.

Uses ``importlib.reload()`` to swap modules in-place so that subsequent tool
calls and core logic pick up the new code without restarting the server.

Regex-watched extension: only ``.py`` files under ``actions/``, ``core/``, and
``agent/`` are tracked.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

# Directories to watch (relative to Lucas root)
_WATCH_DIRS: list[str] = ["actions", "core", "agent"]
_LUCAS_ROOT = Path(__file__).resolve().parent.parent

# Track file modification times  {absolute_path: mtime}
_file_mtimes: dict[str, float] = {}

# Map absolute file paths to Python module names (e.g. "actions.file_controller")
_PATH_TO_MODULE: dict[str, str] = {}

# Modules under ``actions/`` that need re-registration in the tool registry
_ACTION_MARKER = "actions."


def _build_path_map() -> None:
    """Build a map of file paths to Python module names for all watched dirs."""
    _PATH_TO_MODULE.clear()
    _file_mtimes.clear()
    for watch_dir in _WATCH_DIRS:
        dir_path = _LUCAS_ROOT / watch_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            rel_path = py_file.relative_to(_LUCAS_ROOT)
            module_name = str(rel_path.with_suffix("")).replace("/", ".")
            _PATH_TO_MODULE[str(py_file)] = module_name
            _file_mtimes[str(py_file)] = py_file.stat().st_mtime


def _reload_module(file_path: str) -> bool:
    """Reload the Python module corresponding to *file_path*.

    Returns ``True`` when a reload was attempted (even if the module hadn't been
    imported yet).  Syntax errors and import failures are logged but do not
    propagate.
    """
    module_name = _PATH_TO_MODULE.get(file_path)
    if not module_name:
        return False

    try:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

        # Re-register action modules in the tool registry
        if module_name.startswith(_ACTION_MARKER):
            _re_register_action(module_name)

        logger.info("[HotReload] Reloaded: %s", module_name)
        return True
    except SyntaxError as exc:
        logger.warning("[HotReload] Syntax error in %s: %s", module_name, exc)
        return False
    except Exception as exc:
        logger.warning("[HotReload] Failed to reload %s: %s", module_name, exc)
        return False


def _re_register_action(module_name: str) -> None:
    """Look up *module_name* in the tool-registry action list and re-register.

    Uses the canonical ``(module_path, func_name, accepts_speak)`` tuples from
    ``agent.tool_registry._ACTION_MODULES`` so that the correct handler function
    name is always used, even when it differs from the schema name (e.g.
    ``screen_processor`` → ``screen_process``).
    """
    try:
        # Late import to avoid circular dependency at startup
        from agent.tool_registry import _ACTION_MODULES, register_module  # type: ignore[import-untyped]

        for mod_path, func_name, accepts_speak in _ACTION_MODULES:
            if mod_path == module_name:
                register_module(module_name, func_name, accepts_speak=accepts_speak)
                logger.info(
                    "[HotReload] Re-registered tool: %s (%s)",
                    module_name,
                    func_name,
                )
                return

        logger.debug(
            "[HotReload] No _ACTION_MODULES entry for %s — skipping re-registration",
            module_name,
        )
    except Exception as exc:
        logger.warning("[HotReload] Failed to re-register %s: %s", module_name, exc)


def _watch_loop(interval: float = 1.0) -> None:
    """Poll watched files for modification and reload changed modules.

    Runs in a daemon thread and exits silently on unexpected errors.
    """
    logger.info("[HotReload] Watching for changes in: %s", ", ".join(_WATCH_DIRS))
    _build_path_map()

    while True:
        time.sleep(interval)
        try:
            for file_path in list(_PATH_TO_MODULE):
                path = Path(file_path)
                if not path.exists():
                    continue
                current_mtime = path.stat().st_mtime
                last_mtime = _file_mtimes.get(file_path, 0.0)

                if current_mtime > last_mtime:
                    _file_mtimes[file_path] = current_mtime
                    _reload_module(file_path)
        except Exception as exc:
            logger.warning("[HotReload] Watch loop error: %s", exc)


def start(interval: float = 1.0) -> None:
    """Start the hot-reloader in a background daemon thread.

    The thread is a daemon so it will not prevent the process from exiting.
    Call once at application startup.
    """
    thread = threading.Thread(
        target=_watch_loop,
        args=(interval,),
        daemon=True,
        name="hot-reloader",
    )
    thread.start()
    logger.info("[HotReload] Started (poll every %.1fs)", interval)
