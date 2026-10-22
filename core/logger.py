"""
Centralized logging configuration for LUCAS.

Usage:
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Tool registered: %s", tool_name)
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


_ROOT_LOGGER_NAME = "lucas"
_LOG_FORMAT = "[%(asctime)s] %(name)s %(levelname)s — %(message)s"
_LOG_DATE_FMT = "%H:%M:%S"
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "lucas.log"
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
_BACKUP_COUNT = 3

_configured = False


def _configure_root() -> None:
    """One-time setup of the root 'lucas' logger."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(logging.DEBUG)

    # ── Console handler (INFO+) ──────────────────────────────────
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FMT))
    root.addHandler(console)

    # ── Rotating file handler (DEBUG+) ───────────────────────────
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_h = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_h.setLevel(logging.DEBUG)
        file_h.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FMT))
        root.addHandler(file_h)
    except OSError:
        # If we can't write logs to disk, console-only is fine.
        root.warning("Could not create log file at %s", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'lucas' namespace.

    Example:
        get_logger("executor")  →  logger named "lucas.executor"
        get_logger(__name__)    →  logger named "lucas.agent.executor"
    """
    _configure_root()
    # Strip leading package prefixes so names stay short.
    short = name.replace("agent.", "").replace("core.", "")
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{short}")
