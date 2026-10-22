"""Proactive companion configuration — load/save memory/proactive_config.json.

Defaults follow SPEC SS5 with the SS10 confirmed budget override
(max_web_searches_per_day raised to 12 while staying bounded).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

CONFIG_FILE: Path = get_base_dir() / "memory" / "proactive_config.json"

DEFAULTS: dict = {
    "version": 1,
    "enabled": True,
    "poll_interval_sec": 900,
    "pacing_minutes": 60,
    "quiet_start": "22:00",
    "quiet_end": "06:00",
    "dnd_enabled": False,
    "dnd_until_iso": None,
    "engagement": {
        "max_speech_per_day": 3,
        "min_minutes_between": 60,
        "respect_ui_mute": True,
    },
    "budget": {
        "max_llm_ticks_per_day": 6,
        "max_web_searches_per_day": 12,
        "max_project_reads_per_day": 6,
        "max_project_files_per_scan": 8,
        "max_file_bytes_per_scan": 4096,
        "max_research_result_chars": 2000,
    },
    "thresholds": {
        "relevance_min": 0.6,
        "research_topic_min": 0.5,
        "not_repeat_days": 3,
        "semantic_enabled": True,
        "semantic_k": 2,            # clamped 0..5
        "semantic_max_chars": 600,  # clamped 128..2000
    },
}


def _deep_merge(base: dict, update: dict) -> dict:
    """Merge nested dicts recursively, preferring values from *update*."""
    merged = dict(base)
    for key, value in update.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(base[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """Load config, merging over DEFAULTS. Creates the file on first run."""
    if not CONFIG_FILE.exists():
        save_config(DEFAULTS)
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("proactive: failed to load config (%s), using defaults", exc)
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return _deep_merge(DEFAULTS, data)


def save_config(data: dict) -> None:
    """Persist config to memory/proactive_config.json."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )