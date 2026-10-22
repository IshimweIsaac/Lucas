"""Tests for vector-backed semantic memory (memory/semantic_memory.py)."""

from __future__ import annotations

import importlib
import sqlite3
import types
from pathlib import Path

import numpy as np
import pytest

import memory.semantic_memory as semantic_memory

PET_VECTOR = [1.0, 0.0, 1.0]
TECH_VECTOR = [0.0, 1.0, 0.0]


def _embedder(mapping: dict[str, list[float]]):
    """Build a fake embed function returning canned vectors by substring match."""

    def embed(text: str) -> list[float]:
        lowered = text.lower()
        for key, vector in mapping.items():
            if key in lowered:
                return vector
        return PET_VECTOR

    return embed


@pytest.fixture()
def sm(tmp_path, monkeypatch):
    """Reload semantic_memory with an isolated DB path; restore afterwards."""
    monkeypatch.setenv("LUCAS_SEMANTIC_DB", str(tmp_path / "sem.db"))
    reloaded = importlib.reload(semantic_memory)
    yield reloaded
    if reloaded._conn is not None:
        reloaded._conn.close()
    monkeypatch.delenv("LUCAS_SEMANTIC_DB", raising=False)
    importlib.reload(semantic_memory)


def _row_count(db_path) -> int:
    """Count memory rows; a never-created DB counts as zero."""
    if not Path(str(db_path)).exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()


def test_remember_persists_row_and_returns_true(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))

    # Act
    result = sm.remember("My cat is named Whiskers")

    # Assert
    assert result is True
    assert _row_count(sm.DB_PATH) == 1


def test_recall_ranks_relevant_above_irrelevant(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(
        sm, "embed_text", _embedder({"cat": PET_VECTOR, "rust": TECH_VECTOR})
    )
    sm.remember("User adopted a cat named Pixel")
    sm.remember("User writes Rust code every weekend")

    # Act
    results = sm.recall("tell me about my cat", k=2)

    # Assert
    assert results, "expected the pet memory above threshold"
    assert "Pixel" in results[0]
    assert all("Rust" not in item for item in results)


def test_remember_graceful_degradation_on_embed_failure(sm, monkeypatch):
    # Arrange
    def boom(text: str) -> list[float]:
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(sm, "embed_text", boom)

    # Act
    result = sm.remember("anything at all")

    # Assert
    assert result is False
    assert _row_count(sm.DB_PATH) == 0


def test_recall_graceful_degradation_on_embed_failure(sm, monkeypatch):
    # Arrange
    def boom(text: str) -> list[float]:
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(sm, "embed_text", boom)
    assert sm.remember("seed row") is False  # DB stays empty

    # Act
    result = sm.recall("any query")

    # Assert
    assert result == []


def test_recall_empty_db_returns_empty_list(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({}))

    # Act
    result = sm.recall("completely unknown topic")

    # Assert
    assert result == []


# ---------------------------------------------------------------------------
# A2 additions: vector cache + CRUD API
# ---------------------------------------------------------------------------

MIXED_VECTOR = [0.7, 0.7, 0.0]
GUITAR_VECTOR = [-1.0, -1.0, -1.0]


def _seed_rows(sm: types.ModuleType, count: int = 27) -> None:
    """Seed *count* rows cycling through three canned vector clusters.

    Requires ``sm.embed_text`` to already be monkeypatched with a mapping for
    the "cat", "rust" and "mixed" keywords.
    """
    for i in range(count):
        if i % 3 == 0:
            text = f"note {i} about cat care"
        elif i % 3 == 1:
            text = f"note {i} about rust code"
        else:
            text = f"note {i} mixed topics today"
        assert sm.remember(text) is True


def _brute_force_recall(
    sm: types.ModuleType, query_vector: list[float], k: int
) -> list[str]:
    """Reference implementation over raw DB rows: cosine + threshold + top-k."""
    conn = sqlite3.connect(str(sm.DB_PATH))
    try:
        rows = conn.execute(
            "SELECT id, text, kind, embedding FROM memories ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()
    qvec = np.asarray(query_vector, dtype=np.float32)
    scored: list[tuple[float, int, str]] = []
    for idx, (_row_id, text, kind, blob) in enumerate(rows):
        vec = np.frombuffer(blob, dtype=np.float32)
        denom = float(np.linalg.norm(vec)) * float(np.linalg.norm(qvec))
        score = (
            0.0 if denom == 0.0 else float(np.dot(qvec.astype(np.float64), vec.astype(np.float64))) / denom
        )
        if score >= sm._MIN_SCORE:
            scored.append((-score, idx, f"[{kind}] {text}"))
    scored.sort()
    return [item[2] for item in scored[:k]]


def test_recall_returns_same_results_as_full_scan(sm, monkeypatch):
    # Arrange
    mapping = {"cat": PET_VECTOR, "rust": TECH_VECTOR, "mixed": MIXED_VECTOR}
    monkeypatch.setattr(sm, "embed_text", _embedder(mapping))
    _seed_rows(sm, 27)

    # Act
    results = sm.recall("cat", k=5)

    # Assert
    expected = _brute_force_recall(sm, PET_VECTOR, 5)
    assert len(results) == len(expected) == 5
    assert results == expected
    assert all("[fact] note" in item and "cat care" in item for item in results)


def test_remember_updates_cache_without_reload(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(
        sm, "embed_text", _embedder({"cat": PET_VECTOR, "rust": TECH_VECTOR})
    )
    sm.remember("User writes Rust code every weekend")
    before = sm.recall("rust", k=3)

    # Act
    sm.remember("User adopted a cat named Pixel")
    after = sm.recall("my cat pixel", k=3)

    # Assert: the freshly remembered row is visible with no reload/rebuild
    assert before == ["[fact] User writes Rust code every weekend"]
    assert after == ["[fact] User adopted a cat named Pixel"]


def test_delete_memory_removes_row_and_cache_entry(sm, monkeypatch):
    # Arrange
    mapping = {"cat": PET_VECTOR, "rust": TECH_VECTOR}
    monkeypatch.setattr(sm, "embed_text", _embedder(mapping))
    sm.remember("User adopted a cat named Pixel")
    sm.remember("User writes Rust code every weekend")
    rows = sm.list_memories()
    target_id = next(r["id"] for r in rows if "Pixel" in r["text"])
    assert sm.recall("cat", k=3)

    # Act
    removed = sm.delete_memory(target_id)
    listed_after = sm.list_memories()
    recalled_after = sm.recall("cat", k=3)

    # Assert
    assert removed is True
    assert all(r["id"] != target_id for r in listed_after)
    assert recalled_after == []
    assert sm.delete_memory(target_id) is False


def test_update_text_reembeds_and_persists(sm, monkeypatch):
    # Arrange
    mapping = {"cat": PET_VECTOR, "guitar": GUITAR_VECTOR}
    base_embed = _embedder(mapping)
    calls = {"n": 0}

    def counting_embed(text: str) -> list[float]:
        calls["n"] += 1
        return base_embed(text)

    monkeypatch.setattr(sm, "embed_text", counting_embed)
    assert sm.remember("User adopted a cat named Pixel") is True
    row_id = sm.list_memories()[0]["id"]
    calls_after_remember = calls["n"]

    # Act
    updated = sm.update_text(row_id, "User bought a guitar named Blaze")
    listed = sm.list_memories()

    # Assert
    assert updated is True
    assert calls["n"] == calls_after_remember + 1  # re-embed happened
    assert any(r["text"] == "User bought a guitar named Blaze" for r in listed)
    assert sm.recall("cat", k=3) == []  # old phrasing no longer matches
    assert "Blaze" in sm.recall("guitar", k=3)[0]


def test_update_text_embed_failure_leaves_row_intact(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))
    assert sm.remember("User adopted a cat named Pixel") is True
    row_id = sm.list_memories()[0]["id"]

    def boom(text: str) -> list[float]:
        raise RuntimeError("embedding service down")

    # Act
    monkeypatch.setattr(sm, "embed_text", boom)
    updated = sm.update_text(row_id, "totally different text")
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))

    # Assert
    assert updated is False
    assert sm.list_memories()[0]["text"] == "User adopted a cat named Pixel"
    assert "Pixel" in sm.recall("cat", k=3)[0]


def test_list_memories_filters_by_substring_case_insensitive(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))
    sm.remember("Progress bar hit 100% complete today")
    sm.remember("snake_case variable naming convention")
    sm.remember("An ordinary row about cats")
    sm.remember("Another ordinary row entirely")

    # Act + Assert: case-insensitive substring
    hits_cat = sm.list_memories(query="CATS")
    assert [r["text"] for r in hits_cat] == ["An ordinary row about cats"]

    # Act + Assert: % is matched literally, not as a wildcard
    hits_pct = sm.list_memories(query="%")
    assert [r["text"] for r in hits_pct] == ["Progress bar hit 100% complete today"]

    # Act + Assert: _ is matched literally, not as a single-char wildcard
    hits_under = sm.list_memories(query="_case variable")
    assert [r["text"] for r in hits_under] == ["snake_case variable naming convention"]

    # Act + Assert: whitespace-only query behaves like list-all
    assert len(sm.list_memories(query="   ")) == 4

    # Act + Assert: clamping bounds (limit min 1, offset min 0)
    assert len(sm.list_memories(limit=-3)) == 1
    assert sm.list_memories(offset=99) == []


def test_count_memories_matches_rows(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))
    sm.remember("A cat fact worth keeping")
    sm.remember("Another cat fact worth keeping")
    sm.remember("Something unrelated altogether")

    # Act
    total = sm.count_memories()
    filtered = sm.count_memories(query="CAT")

    # Assert
    assert total == 3
    assert filtered == 2
    assert sm.count_memories(query="zzz-no-match") == 0
    assert total == _row_count(sm.DB_PATH)


def test_cache_staleness_rebuild_on_external_insert(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(
        sm, "embed_text", _embedder({"cat": PET_VECTOR, "rust": TECH_VECTOR})
    )
    assert sm.remember("User writes Rust code every weekend") is True
    assert sm.list_memories()  # builds the cache
    blob = np.asarray(PET_VECTOR, dtype=np.float32).tobytes()
    external_conn = sqlite3.connect(str(sm.DB_PATH))
    try:
        external_conn.execute(
            "INSERT INTO memories(text, kind, embedding, created_at)"
            " VALUES(?, ?, ?, ?)",
            ("Out-of-band note about a cat named Mochi", "fact", blob, "2026-08-22 00:00:00"),
        )
        external_conn.commit()
    finally:
        external_conn.close()

    # Act
    listed = sm.list_memories()
    recalled = sm.recall("cat", k=3)

    # Assert: COUNT-guard rebuild surfaced the out-of-band row everywhere
    assert any("Mochi" in r["text"] for r in listed)
    assert recalled == ["[fact] Out-of-band note about a cat named Mochi"]


def test_recall_scores_outside_the_lock(sm, monkeypatch):
    # Arrange
    monkeypatch.setattr(sm, "embed_text", _embedder({"cat": PET_VECTOR}))
    assert sm.remember("User adopted a cat named Pixel") is True
    lock_state = {}
    real_score = sm._score_snapshot

    def spy(snapshot, query_vec):
        acquired = sm._lock.acquire(blocking=False)
        lock_state["held_by_caller"] = not acquired
        if acquired:
            sm._lock.release()
        return real_score(snapshot, query_vec)

    monkeypatch.setattr(sm, "_score_snapshot", spy)

    # Act
    results = sm.recall("cat", k=3)

    # Assert
    assert results
    assert lock_state["held_by_caller"] is False
