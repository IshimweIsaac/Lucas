"""Rate-limited, strictly non-secret project + memory reading for the curator.

Only reads: registered project roots' allow-listed metadata files (stat-light,
shallow), long-term memory categories, the session brief, and notes. Never
touches config/, .git internals, secrets, keys, tokens, pem, or env files.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from core.logger import get_logger
from core import path_utils
from memory import memory_manager
from memory import session_brief

logger = get_logger(__name__)

ALLOWED_FILENAMES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "README.md",
        "readme.md",
        "pyproject.toml",
        "Cargo.toml",
        "package.json",
    }
)

BLOCKLIST_SUBSTR: tuple[str, ...] = (
    "config/",
    ".git",
    "secret",
    "token",
    ".key",
    ".pem",
    ".env",
    "api_keys",
)

_MEMORY_CATEGORIES = ("preferences", "interests", "projects", "wishes", "notes")


def registry() -> list[str]:
    """Registered project roots the scanner may look at."""
    try:
        return path_utils.known_paths()
    except Exception as exc:
        logger.warning("proactive: known_paths failed (%s)", exc)
        return []


def is_allowed_path(path: Path) -> bool:
    """Blocklist filter: reject config/, .git, secret/token/key/pem/env paths."""
    try:
        if not path.is_file():
            return False
    except OSError:
        return False
    low = str(path).lower()
    return not any(seg in low for seg in BLOCKLIST_SUBSTR)


def _safe_memory_value(value) -> str:
    text = value.get("value") if isinstance(value, dict) else value
    text = str(text or "").strip()
    low = text.lower()
    if any(seg in low for seg in BLOCKLIST_SUBSTR):
        return ""
    return text[:380]


def _collect_memory() -> tuple[dict, list[str]]:
    memory = memory_manager.load_memory()
    out: dict = {}
    seen: list[str] = []
    for cat in _MEMORY_CATEGORIES:
        items = memory.get(cat, {})
        if not isinstance(items, dict):
            continue
        kept: dict = {}
        for key, entry in items.items():
            text = _safe_memory_value(entry)
            if not text:
                continue
            if any(seg in key.lower() for seg in BLOCKLIST_SUBSTR):
                continue
            kept[key] = text
            seen.append(f"memory:{cat}:{key}")
        if kept:
            out[cat] = kept
    return out, seen


def _collect_brief() -> tuple[str, list[str]]:
    try:
        text = session_brief.format_for_prompt() or ""
    except Exception as exc:
        logger.warning("proactive: session brief read failed (%s)", exc)
        return "", []
    if not text.strip():
        return "", []
    return text, ["brief"]


def _collect_notes(max_chars: int) -> tuple[list[dict], list[str]]:
    try:
        from core import notes_core

        notes = notes_core._load_json(notes_core._NOTES_FILE)
    except Exception as exc:
        logger.warning("proactive: notes read failed (%s)", exc)
        return [], []
    if not isinstance(notes, list):
        return [], []
    out: list[dict] = []
    seen: list[str] = []
    total = 0
    for note in notes:
        if not isinstance(note, dict):
            continue
        title = str(note.get("title") or "")[:120]
        content = str(note.get("content") or "")
        low = (title + " " + content).lower()
        if any(seg in low for seg in BLOCKLIST_SUBSTR):
            continue
        text = (title + "\n" + content).strip()[:max_chars]
        if not text:
            continue
        out.append({"path": f"notes:{title}", "text": text})
        seen.append(f"notes:{title}")
        total += len(text)
        if total > max_chars * 2:
            break
    return out, seen


def _clamp_semantic_cfg(cfg: dict | None) -> tuple[bool, int, int]:
    """Defensive read + clamp of semantic thresholds.

    Persisted values may be out of range (the proactive __init__ clamp cannot
    be extended from here), so enforce k 0..5 and max_chars 128..2000 at the
    point of consumption.
    """
    thresholds = (cfg or {}).get("thresholds", {})
    if not isinstance(thresholds, dict):
        return False, 0, 600
    enabled = bool(thresholds.get("semantic_enabled", True))
    try:
        k = max(0, min(5, int(thresholds.get("semantic_k", 2))))
    except (TypeError, ValueError):
        k = 2
    try:
        max_chars = max(
            128, min(2000, int(thresholds.get("semantic_max_chars", 600)))
        )
    except (TypeError, ValueError):
        max_chars = 600
    return enabled, k, max_chars


def _semantic_kind(recalled: str) -> str:
    """Parse "[kind] text" labels; default to "fact" when unparseable."""
    match = re.match(r"\[([^\]]+)\]", recalled)
    if not match:
        return "fact"
    kind = match.group(1).strip()[:40]
    return kind or "fact"


def _collect_semantic(cfg: dict | None) -> tuple[list[dict], list[str]]:
    """Semantic-memory nudge source: recall past statements relevant to today/tomorrow."""
    enabled, k, max_chars = _clamp_semantic_cfg(cfg)
    if not enabled or k <= 0:
        return [], []

    now = datetime.now()
    tomorrow_key = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    query_parts: list[str] = [now.strftime("%A")]
    try:
        from core import calendar_store

        cal = calendar_store.load()
        upcoming = calendar_store.iter_today_upcoming(cal)
        primary = upcoming[0].description if upcoming else now.strftime("%A")
        query_parts = [primary]
        for ev in cal.get("events_by_date", {}).get(tomorrow_key, []):
            desc = str((ev or {}).get("description") or "")
            if desc:
                query_parts.append(desc)
    except Exception as exc:
        logger.warning("proactive: calendar read failed (%s)", exc)

    try:
        from memory import semantic_memory

        hits = semantic_memory.recall(" ".join(query_parts), k=k)
    except Exception as exc:
        logger.warning("proactive: semantic recall failed (%s)", exc)
        return [], []

    items: list[dict] = []
    seen: list[str] = []
    total = 0
    per_hit_chars = max(1, max_chars // k)
    for hit in hits:
        text = str(hit or "").strip()
        low = text.lower()
        if not text or any(seg in low for seg in BLOCKLIST_SUBSTR):
            continue
        trimmed = text[:per_hit_chars]
        if total + len(trimmed) > max_chars:
            break
        kind = _semantic_kind(text)
        items.append({"path": f"semantic:{kind}", "text": trimmed})
        seen.append(f"semantic:{kind}:{len(items) - 1}")
        total += len(trimmed)
    return items, seen


def collect_sources(cfg: dict | None = None) -> dict:
    """Collect safe, bounded context blobs for the curator.

    Budgets come from cfg.budget: max_project_reads_per_day dirs,
    max_project_files_per_scan files, max_file_bytes_per_scan bytes/file.
    """
    budget = (cfg or {}).get("budget", {})
    max_dirs = int(budget.get("max_project_reads_per_day", 6))
    max_files = int(budget.get("max_project_files_per_scan", 8))
    max_bytes = int(budget.get("max_file_bytes_per_scan", 4096))

    projects: list[dict] = []
    seen: list[str] = []
    file_count = 0
    for root in registry()[:max_dirs]:
        root_path = Path(root)
        found: list[dict] = []
        for name in sorted(ALLOWED_FILENAMES):
            if file_count >= max_files:
                break
            candidate = root_path / name
            if not is_allowed_path(candidate):
                continue
            try:
                if candidate.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("proactive: read %s failed (%s)", candidate, exc)
                continue
            if not text.strip():
                continue
            found.append({"path": str(candidate), "text": text[:max_bytes]})
            seen.append(f"scanner:{candidate}")
            file_count += 1
        if found:
            projects.append({"root": root, "files": found})

    memory, mem_seen = _collect_memory()
    brief, brief_seen = _collect_brief()
    notes, notes_seen = _collect_notes(max_bytes)
    sem_items, sem_seen = _collect_semantic(cfg)

    seen = seen + mem_seen + brief_seen + notes_seen + sem_seen
    logger.info(
        "proactive: scan read %d project file(s), %d memory key(s), "
        "%d note(s)",
        file_count,
        len(mem_seen),
        len(notes_seen),
    )
    return {
        "projects": projects,
        "memory": memory,
        "brief": brief,
        "notes": notes,
        "semantic": sem_items,
        "sources_seen": seen,
    }


def collect_memory_sources() -> dict:
    """Memory/notes-only fallback when no project roots are registered."""
    memory, mem_seen = _collect_memory()
    brief, brief_seen = _collect_brief()
    notes, notes_seen = _collect_notes(4096)
    sem_items, sem_seen = _collect_semantic(None)
    return {
        "projects": [],
        "memory": memory,
        "brief": brief,
        "notes": notes,
        "semantic": sem_items,
        "sources_seen": mem_seen + brief_seen + notes_seen + sem_seen,
    }