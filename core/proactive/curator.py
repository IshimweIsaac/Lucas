"""Thinker/Curator — offline-first insight generation.

Calls gemini_text (flash-lite) to synthesize 1-3 candidate observations from
scanner sources, scores each deterministically (relevance.py), and returns the
best candidate above threshold. On any LLM failure it falls back to a
deterministic local candidate so the engine never crashes and never lies
about having read sources it did not read.
"""

from __future__ import annotations

import json
import re

from core.logger import get_logger
from core.proactive import engagement_store
from core.proactive import persona
from core.proactive import relevance

logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-3.1-flash-lite"

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_KEY_PATTERN = re.compile(r"[A-Za-z0-9_\-]{20,}")


def _fmt_sources(sources: dict, max_chars: int = 4000) -> str:
    """Flatten scanner sources into a bounded, human-readable context block."""
    chunks: list[str] = []

    for project in sources.get("projects", []) or []:
        for file in project.get("files", []) or []:
            text = (file.get("text") or "").strip()
            if text:
                chunks.append(f"[{file.get('path', '')}]\n{text}")

    memory = sources.get("memory", {}) or {}
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, value in items.items():
            chunks.append(f"memory:{cat}:{key} = {value}")

    brief = (sources.get("brief") or "").strip()
    if brief:
        chunks.append(f"[SESSION BRIEF]\n{brief}")

    for note in sources.get("notes", []) or []:
        text = (note.get("text") or "").strip()
        if text:
            chunks.append(f"[{note.get('path', 'note')}]\n{text}")

    for hit in sources.get("semantic", []) or []:
        text = (hit.get("text") or "").strip()
        if text:
            chunks.append(f"[{hit.get('path', 'semantic')}]\n{text}")

    out = "\n\n".join(chunks)
    if len(out) > max_chars:
        out = out[: max_chars - 3].rstrip() + "\n..."
    return out


def _scrub(text: str) -> str:
    """Remove anything that looks like an API key/secret token before returning."""
    return _KEY_PATTERN.sub("[redacted]", text or "")


def _parse_candidates(raw: str) -> list[dict]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        logger.warning("proactive: curator JSON parse failed (%s)", exc)
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title and not body:
            continue
        out.append(
            {
                "kind": str(item.get("kind") or "insight")[:20],
                "title": title[:160] or body[:80],
                "body": _scrub(body[:600]),
                "source": _scrub(str(item.get("source") or "")[:200]),
            }
        )
    return out


def _score_candidates(candidates: list[dict], sources_text: str) -> list[dict]:
    history = engagement_store.recent_topics(10)
    for candidate in candidates:
        candidate["score"] = relevance.relevance_score(
            candidate["title"] + " " + candidate["body"],
            sources=[sources_text],
            history=history,
        )
    return candidates


def _local_fallback(sources: dict) -> list[dict]:
    """Deterministic memory-only candidate when the LLM cannot be reached."""
    memory = sources.get("memory", {}) or {}
    texts: list[str] = []
    labels: list[str] = []
    for cat in ("interests", "preferences", "projects", "wishes", "notes"):
        for key, value in (memory.get(cat, {}) or {}).items():
            texts.append(f"{key} {value}")
            labels.append(f"memory:{cat}:{key}")
    if not texts:
        return []
    best = max(texts, key=lambda t: relevance.relevance_score(t, sources=texts))
    index = texts.index(best)
    title = best[:80]
    return [
        {
            "kind": "question",
            "title": title,
            "body": (
                f"May I ask about {title}? "
                "I have been thinking about it, sir."
            )[:300],
            "source": labels[index],
        }
    ]


def _generate_with_agent_key(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
) -> str:
    """Lazy import avoids import cycles with agent/tool_registry at load time."""
    from memory import gemini_text

    return gemini_text.generate_text_with_agent_key(
        model=model,
        contents=contents,
        system_instruction=system_instruction,
    )


def generate_candidates(
    *,
    sources: dict,
    cfg: dict | None = None,
    counters: dict | None = None,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Generate scored candidate insights from local sources (offline-first)."""
    context = _fmt_sources(sources)
    if not context.strip():
        return _local_fallback(sources)

    digest = engagement_store.digest(3)
    prompt = (
        "You are Lucas' proactive thinking engine. Read the local context "
        "below and produce 1-3 candidate observations or curious questions "
        "for the user, derived ONLY from this context.\n"
        "Rules:\n"
        "- Return ONLY a JSON array of objects: "
        '{"kind": "insight|question|research|proposal", "title": "short", '
        '"body": "one concise item, at most 3 sentences, framed as '
        '\'may I share\' / \'may I ask\'", "source": "memory:<cat>:<key>, '
        'scanner:<path>, or semantic:<kind> (past user statement)"}\n'
        "- Never mention secrets, config/, or API keys.\n"
        "- Never repeat the recent engagements.\n"
        "Context:\n"
        f"{context}\n\n"
        f"Recent engagements:\n{digest}\n"
    )
    try:
        raw = _generate_with_agent_key(
            model=model,
            contents=prompt,
            system_instruction=persona.persona_block(),
        )
    except Exception as exc:
        logger.warning("proactive: curator LLM failed (%s), local fallback", exc)
        return _local_fallback(sources)

    candidates = _parse_candidates(raw)
    if not candidates:
        return _local_fallback(sources)
    return _score_candidates(candidates, context)


def pick_best(
    candidates: list[dict],
    cfg: dict | None = None,
    history: list[str] | None = None,
) -> dict | None:
    """Return the highest-scoring candidate above the relevance threshold."""
    min_score = float((cfg or {}).get("thresholds", {}).get("relevance_min", 0.6))
    history = history if history is not None else engagement_store.recent_topics(8)
    eligible = [
        c
        for c in candidates
        if float(c.get("score", 0.0)) >= min_score
        and not relevance.is_repeated(c.get("title", ""), history)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
    return eligible[0]