"""Gemini text models — separate quotas from voice (Live API)."""

from __future__ import annotations

import json

from memory.config_manager import get_base_dir

PROFILE_PATH = get_base_dir() / "memory" / "coding_profile.json"
DEFAULT_LITE_MODEL = "gemini-3.1-flash-lite"
DEFAULT_CODING_MODEL = DEFAULT_LITE_MODEL
DEFAULT_SEARCH_MODEL = DEFAULT_LITE_MODEL


def _profile_models() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_coding_model() -> str:
    model = (_profile_models().get("coding_model") or "").strip()
    return model or DEFAULT_CODING_MODEL


def get_search_model() -> str:
    data = _profile_models()
    model = (data.get("search_model") or data.get("coding_model") or "").strip()
    return model or DEFAULT_SEARCH_MODEL
