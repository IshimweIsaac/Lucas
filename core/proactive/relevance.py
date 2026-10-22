"""Deterministic relevance scoring for proactive candidates.

Pure functions (no I/O) so the curator can score candidate insights against
scanned sources, penalize repeats from engagement history, and filter to a
threshold before anything is spoken.
"""

from __future__ import annotations

import re

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "your", "that", "this",
        "with", "have", "from", "they", "will", "would", "there", "about",
        "what", "when", "where", "which", "their", "them", "its", "into",
        "than", "then", "these", "those", "sir", "may", "can", "ask", "share",
        "should", "could", "does", "dont", "just", "one", "also", "been",
        "being", "were", "was", "has", "had", "him", "his", "her", "our",
    }
)


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def is_repeated(
    topic: str, history: list[str], not_repeat_days: int = 3
) -> bool:
    """True when *topic* substantially overlaps any recent engagement topic."""
    if not history:
        return False
    topic_tokens = _tokenize(topic)
    if not topic_tokens:
        return False
    for past in history:
        past_tokens = _tokenize(past)
        if not past_tokens:
            continue
        overlap = len(topic_tokens & past_tokens)
        if overlap / len(past_tokens) >= 0.6 or overlap / len(topic_tokens) >= 0.6:
            return True
    return False


def relevance_score(
    candidate: str,
    *,
    sources: list[str],
    history: list[str] | None = None,
    not_repeat_days: int = 3,
) -> float:
    """Jaccard token overlap between the candidate and scanned sources.

    Repeats are penalized to 40% of the raw score so recently-said topics
    rarely win unless strongly backed by fresh source overlap.
    """
    cand_tokens = _tokenize(candidate)
    if not cand_tokens:
        return 0.0
    src_tokens = _tokenize(" ".join(sources))
    if not src_tokens:
        return 0.1
    union = cand_tokens | src_tokens
    score = (len(cand_tokens & src_tokens) / len(union)) if union else 0.0
    if is_repeated(candidate, list(history or []), not_repeat_days):
        score *= 0.4
    return round(max(0.0, min(1.0, score)), 3)