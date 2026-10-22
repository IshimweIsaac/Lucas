"""Proactive companion engine — public API.

`run()` is the supervisor-loop entry: governor -> scanner -> curator ->
research -> delivery decision. The remaining functions back the `proactive`
tool (status / on_your_mind / dismiss / history / configure / budget /
research_topic).

SPEC: docs at ~/.opencode/sessions/2026-08-08-lucas-proactive-companion/SPEC.md
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from core.proactive import config
from core.proactive import curator
from core.proactive import engagement_store
from core.proactive import governor
from core.proactive import project_research
from core.proactive import research_ideas_store
from core.proactive import scanner

logger = get_logger(__name__)

__all__ = [
    "config",
    "curator",
    "engagement_store",
    "governor",
    "project_research",
    "research_ideas_store",
    "scanner",
    "run",
    "status",
    "configure",
    "on_your_mind",
    "history",
    "budget",
    "dismiss",
    "research_now",
    "queue_trigger",
    "current_card",
]

_QUIET_REASON = "quiet hours"


async def run(
    *,
    tick: datetime | None = None,
    muted: bool = False,
    session_ok: bool = True,
    idle_seconds: int | None = None,
) -> dict | None:
    """One full proactive pass. Returns an engagement card when the engine
    produced something worth surfacing, else None.

    Delivery decision is encoded in the returned dict: `deliver=True` means
    the caller should speak it now; `deliver=False` means a trigger file was
    queued for the trigger watcher (muted/idle/busy path).
    """
    cfg = config.load_config()
    if not cfg.get("enabled", True):
        return None

    counters = engagement_store.get_daily_counters()
    ok, reason = governor.can_work(cfg, counters, now=tick)
    if not ok:
        logger.info("PROACTIVE SKIPPED: %s", reason)
        return None

    sources = await asyncio.to_thread(scanner.collect_sources, cfg)
    engagement_store.bump_counter("reads")

    candidates = await asyncio.to_thread(
        curator.generate_candidates, sources=sources, cfg=cfg, counters=counters
    )
    card = curator.pick_best(
        candidates, cfg=cfg, history=engagement_store.recent_topics(8)
    )
    entry_id: str | None = None
    if card:
        engagement_store.bump_counter("llm")
        entry = engagement_store.append_entry(
            {
                "kind": card.get("kind", "insight"),
                "title": card.get("title", ""),
                "body": card.get("body", ""),
                "score": float(card.get("score", 0.0)),
                "source": card.get("source", ""),
                "status": "queued",
            }
        )
        entry_id = entry.get("id")

    research = await asyncio.to_thread(
        project_research.maybe_research, cfg=cfg, counters=counters
    )
    if research:
        engagement_store.bump_counter("web")
        engagement_store.append_entry(
            {
                "kind": "research",
                "title": research.get("topic", ""),
                "body": research.get("result", ""),
                "score": 0.0,
                "source": "research_ideas:" + str(research.get("id", "")),
                "status": "queued",
            }
        )

    if entry_id is None:
        return None

    idle = idle_seconds
    if idle is None:
        idle = _user_idle_seconds(session_ok)
    ok_speak, speak_reason = governor.allowed_to_speak(
        cfg, counters, muted=muted, idle_seconds=idle, now=tick
    )
    title = card.get("title", "")
    body = card.get("body", "") or title
    if ok_speak and session_ok:
        engagement_store.mark_status(entry_id, "spoken")
        engagement_store.bump_counter("speech")
        return {
            "id": entry_id,
            "kind": card.get("kind", "insight"),
            "title": title,
            "body": body,
            "score": float(card.get("score", 0.0)),
            "source": card.get("source", ""),
            "deliver": True,
            "reason": "ok",
        }

    queue_trigger(f"[LUCAS PROACTIVE]\n{title}\n{body}")
    return {
        "id": entry_id,
        "kind": card.get("kind", "insight"),
        "title": title,
        "body": body,
        "score": float(card.get("score", 0.0)),
        "source": card.get("source", ""),
        "deliver": False,
        "reason": speak_reason,
    }


def _user_idle_seconds(session_ok: bool) -> int:
    if not session_ok:
        return 0
    try:
        from core import context_engine

        return int(context_engine.get_context().get("user_idle_seconds", 0) or 0)
    except Exception as exc:
        logger.warning("proactive: context read failed (%s)", exc)
        return 0


def queue_trigger(message: str) -> Path:
    """Write a trigger file for main.py's _watch_triggers to pick up."""
    trigger_dir = Path.home() / ".lucas" / "triggers"
    trigger_dir.mkdir(parents=True, exist_ok=True)
    path = trigger_dir / f"trigger_proactive_{time.time_ns()}_{os.getpid()}.json"
    path.write_text(
        json.dumps({"message": message, "source": "proactive"}),
        encoding="utf-8",
    )
    logger.info("proactive: queued trigger %s", path.name)
    return path


def current_card() -> dict | None:
    """Most recent pending engagement (queued/spoken), if any."""
    entry = engagement_store.last_engagement()
    if entry and entry.get("status") in {"queued", "spoken"}:
        return entry
    return None


def on_your_mind() -> str:
    """The non-generating path: report the current curated card, or stay quiet.

    Never calls the LLM or web — safe to invoke any time.
    """
    card = current_card()
    if not card:
        return "engine quiet: nothing to say yet"
    title = card.get("title") or ""
    body = card.get("body") or title
    return f"[LUCAS PROACTIVE] {title}\n{body}"


def status() -> str:
    """Human summary: config state + budget counters + last engagement."""
    cfg = config.load_config()
    counters = engagement_store.get_daily_counters()
    quiet = f"{cfg.get('quiet_start')} - {cfg.get('quiet_end')}"
    dnd = "on" if governor.dnd_active(cfg) else "off"
    last = engagement_store.last_engagement()
    last_line = "none"
    if last:
        last_line = f"{last.get('title', 'untitled')} [{last.get('status')}]"
    lines = [
        f"enabled: {cfg.get('enabled')}",
        f"poll interval: {cfg.get('poll_interval_sec')}s",
        f"pacing: {cfg.get('pacing_minutes')} min",
        f"quiet window: {quiet}",
        f"dnd: {dnd}",
        f"budget today: llm {counters.get('llm', 0)}/{cfg.get('budget', {}).get('max_llm_ticks_per_day', 6)}, "
        f"web {counters.get('web', 0)}/{cfg.get('budget', {}).get('max_web_searches_per_day', 12)}, "
        f"reads {counters.get('reads', 0)}/{cfg.get('budget', {}).get('max_project_reads_per_day', 6)}, "
        f"speech {counters.get('speech', 0)}/{cfg.get('engagement', {}).get('max_speech_per_day', 3)}",
        f"last engagement: {last_line}",
    ]
    return "\n".join(lines)


def budget() -> str:
    """Budget caps vs today's usage."""
    cfg = config.load_config()
    counters = engagement_store.get_daily_counters()
    b = cfg.get("budget", {})
    e = cfg.get("engagement", {})
    return (
        f"llm: {counters.get('llm', 0)}/{b.get('max_llm_ticks_per_day', 6)}\n"
        f"web: {counters.get('web', 0)}/{b.get('max_web_searches_per_day', 12)}\n"
        f"reads: {counters.get('reads', 0)}/{b.get('max_project_reads_per_day', 6)}\n"
        f"speech: {counters.get('speech', 0)}/{e.get('max_speech_per_day', 3)}"
    )


def history(limit: int = 10) -> str:
    entries = engagement_store.recent_entries(limit)
    if not entries:
        return "No proactive engagements yet."
    lines = []
    for entry in entries:
        lines.append(
            f"- {entry.get('id')} [{entry.get('status')}] "
            f"{entry.get('at', '')}: {entry.get('title', 'untitled')}"
        )
    return "\n".join(lines)


def dismiss(entry_id: str) -> str:
    if engagement_store.mark_status(entry_id, "dismissed"):
        return f"Dismissed {entry_id}"
    return f"Not found: {entry_id}"


def research_now(topic: str, *, manual: bool = True) -> str:
    """Manual research — user-requested topics are never throttled."""
    return project_research.research_topic(topic, manual=manual)


def configure(params: dict) -> str:
    """Validate and persist allowed config changes; report what changed."""
    if not isinstance(params, dict) or not params:
        return "No settings provided."
    cfg = config.load_config()
    changed: list[str] = []
    unknown: list[str] = []

    for key, value in params.items():
        if key == "enabled" and isinstance(value, bool):
            cfg["enabled"] = value
            changed.append("enabled")
        elif key == "poll_interval_sec" and isinstance(value, int):
            cfg["poll_interval_sec"] = max(60, int(value))
            changed.append("poll_interval_sec")
        elif key == "pacing_minutes" and isinstance(value, int):
            cfg["pacing_minutes"] = max(10, int(value))
            changed.append("pacing_minutes")
        elif key in ("quiet_start", "quiet_end") and isinstance(value, str):
            if _valid_hhmm(value):
                cfg[key] = value.strip()
                changed.append(key)
            else:
                unknown.append(f"{key} (bad HH:MM)")
        elif key == "dnd_enabled" and isinstance(value, bool):
            cfg["dnd_enabled"] = value
            changed.append("dnd_enabled")
        elif key == "dnd_until_iso":
            if value is None:
                cfg["dnd_until_iso"] = None
                changed.append("dnd_until_iso")
            elif isinstance(value, str) and _valid_iso(value):
                cfg["dnd_until_iso"] = value
                changed.append("dnd_until_iso")
            else:
                unknown.append("dnd_until_iso (bad ISO)")
        elif key in ("engagement", "budget", "thresholds") and isinstance(
            value, dict
        ):
            merged = dict(cfg.get(key, {}))
            for sub_key, sub_value in value.items():
                merged[sub_key] = sub_value
            cfg[key] = _clamp_section(key, merged)
            changed.append(key)
        else:
            unknown.append(str(key))

    config.save_config(cfg)
    if changed:
        return "Configured: " + ", ".join(sorted(changed))
    return "No valid settings. Ignored: " + (", ".join(unknown) or "none")


def _valid_hhmm(value: str) -> bool:
    try:
        hours, minutes = value.strip().split(":")
        return 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59
    except (ValueError, AttributeError):
        return False


def _valid_iso(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _clamp_section(section: str, values: dict) -> dict:
    """Clamp numeric settings into sane ranges before persisting."""
    out = dict(values)
    if section == "engagement":
        out["max_speech_per_day"] = max(1, int(out.get("max_speech_per_day", 3)))
        out["min_minutes_between"] = max(5, int(out.get("min_minutes_between", 60)))
        out["respect_ui_mute"] = bool(out.get("respect_ui_mute", True))
    elif section == "budget":
        for key, default in (
            ("max_llm_ticks_per_day", 6),
            ("max_web_searches_per_day", 12),
            ("max_project_reads_per_day", 6),
            ("max_project_files_per_scan", 8),
        ):
            out[key] = max(1, int(out.get(key, default)))
        out["max_file_bytes_per_scan"] = max(256, int(out.get("max_file_bytes_per_scan", 4096)))
        out["max_research_result_chars"] = max(256, int(out.get("max_research_result_chars", 2000)))
    elif section == "thresholds":
        for key in ("relevance_min", "research_topic_min"):
            value = float(out.get(key, 0.6 if key == "relevance_min" else 0.5))
            out[key] = max(0.0, min(1.0, value))
        out["not_repeat_days"] = max(1, int(out.get("not_repeat_days", 3)))
    return out