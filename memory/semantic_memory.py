"""Vector-backed semantic memory: SQLite rows + Gemini embeddings + cosine recall."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from core.logger import get_logger
from memory.config_manager import get_base_dir
from memory.gemini_embed import embed_text

logger = get_logger(__name__)

_db_override = os.environ.get("LUCAS_SEMANTIC_DB", "")
if _db_override:
    DB_PATH = Path(_db_override)
else:
    DB_PATH = get_base_dir() / "memory" / "semantic_memory.db"

_MIN_SCORE = 0.25
_PROMPT_HEADER = "[SEMANTIC MEMORY — past facts relevant to current topic]"
_LIST_LIMIT_MAX = 500

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


class _CacheSnapshot:
    """Immutable in-memory copy of the memories table for lock-free scoring.

    Writers build a fresh snapshot and swap it in under ``_lock``; readers grab
    one reference and score against it without holding the lock.
    """

    __slots__ = ("ids", "texts", "kinds", "created_ats", "matrix", "version")

    def __init__(
        self,
        ids: list[int],
        texts: list[str],
        kinds: list[str],
        created_ats: list[str],
        matrix: np.ndarray,
        version: int,
    ) -> None:
        self.ids = ids  # ascending id order, aligned with every list below
        self.texts = texts
        self.kinds = kinds
        self.created_ats = created_ats
        self.matrix = matrix  # float32 N x D; N == 0 when the table is empty
        self.version = version


_cache: _CacheSnapshot | None = None


def _get_conn() -> sqlite3.Connection:
    """Open (once) the SQLite connection and ensure the schema exists."""
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memories("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "text TEXT NOT NULL,"
            "kind TEXT NOT NULL DEFAULT 'fact',"
            "embedding BLOB NOT NULL,"
            "created_at TEXT NOT NULL)"
        )
        conn.commit()
        _conn = conn
    return _conn


def _snapshot_from_db(version: int) -> _CacheSnapshot:
    """Read every row into a fresh snapshot. Caller holds ``_lock``."""
    rows = _get_conn().execute(
        "SELECT id, text, kind, created_at, embedding FROM memories ORDER BY id ASC"
    ).fetchall()
    if rows:
        vectors = [np.frombuffer(row[4], dtype=np.float32) for row in rows]
        matrix = np.vstack(vectors).astype(np.float32, copy=False)
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
    return _CacheSnapshot(
        ids=[row[0] for row in rows],
        texts=[row[1] for row in rows],
        kinds=[row[2] for row in rows],
        created_ats=[row[3] for row in rows],
        matrix=matrix,
        version=version,
    )


def _ensure_fresh_cache_locked() -> _CacheSnapshot | None:
    """Return a current snapshot, rebuilding when the DB diverges from cache."""
    global _cache
    try:
        total = _get_conn().execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        cached = len(_cache.ids) if _cache is not None else -1
        if _cache is None or total != cached:
            next_version = (_cache.version + 1) if _cache is not None else 1
            _cache = _snapshot_from_db(next_version)
    except Exception as e:
        logger.warning("Semantic cache refresh failed: %s", e)
        _cache = None
    return _cache


def _append_to_cache_locked(
    row_id: int, text: str, kind: str, created: str, vector: np.ndarray
) -> None:
    """Append one remembered row to the live snapshot. Caller holds ``_lock``."""
    global _cache
    snap = _cache
    if snap is None:
        return  # cache not built yet; the next reader loads everything from DB
    try:
        if snap.matrix.shape[0] == 0:
            matrix = vector.reshape(1, -1).astype(np.float32, copy=False)
        else:
            matrix = np.vstack([snap.matrix, vector.reshape(1, -1)])
        _cache = _CacheSnapshot(
            [*snap.ids, row_id],
            [*snap.texts, text],
            [*snap.kinds, kind],
            [*snap.created_ats, created],
            matrix.astype(np.float32, copy=False),
            snap.version + 1,
        )
    except Exception as e:
        logger.warning("Semantic cache append failed: %s", e)
        _cache = None  # force a clean rebuild on the next read


def _drop_from_cache_locked(row_id: int) -> None:
    """Remove one deleted row from the live snapshot. Caller holds ``_lock``."""
    global _cache
    snap = _cache
    if snap is None:
        return
    try:
        pos = snap.ids.index(row_id)
    except ValueError:
        return  # entry already absent; COUNT guard heals any real divergence
    kept = [j for j in range(len(snap.ids)) if j != pos]
    mask = np.ones(snap.matrix.shape[0], dtype=bool)
    mask[pos] = False
    _cache = _CacheSnapshot(
        [snap.ids[j] for j in kept],
        [snap.texts[j] for j in kept],
        [snap.kinds[j] for j in kept],
        [snap.created_ats[j] for j in kept],
        snap.matrix[mask].astype(np.float32, copy=False),
        snap.version + 1,
    )


def _replace_in_cache_locked(row_id: int, text: str, vector: np.ndarray) -> None:
    """Rewrite one edited row's text and embedding. Caller holds ``_lock``."""
    global _cache
    snap = _cache
    if snap is None:
        return
    try:
        pos = snap.ids.index(row_id)
    except ValueError:
        return  # stale cache; COUNT guard rebuilds with DB truth later
    try:
        matrix = snap.matrix.copy()
        matrix[pos] = vector
    except Exception as e:
        logger.warning("Semantic cache update failed: %s", e)
        _cache = None
        return
    texts = list(snap.texts)
    texts[pos] = text
    _cache = _CacheSnapshot(
        list(snap.ids),
        texts,
        list(snap.kinds),
        list(snap.created_ats),
        matrix,
        snap.version + 1,
    )


def _score_snapshot(snapshot: _CacheSnapshot, query_vec: np.ndarray) -> np.ndarray:
    """Cosine-score every cached row via one matmul. No lock held here."""
    qnorm = float(np.linalg.norm(query_vec))
    scores = np.zeros(snapshot.matrix.shape[0], dtype=np.float64)
    if qnorm == 0.0 or snapshot.matrix.shape[0] == 0:
        return scores
    dots = snapshot.matrix @ query_vec
    denom = np.linalg.norm(snapshot.matrix, axis=1) * qnorm
    valid = denom > 0.0
    scores[valid] = dots[valid].astype(np.float64) / denom[valid]
    return scores


def _top_k_indices(scores: np.ndarray, k: int) -> list[int]:
    """Indices of the best *k* scores at/above threshold, best-first.

    Uses argpartition to avoid a full sort, then sorts only the candidate
    subset. Ties resolve to the lower index (ascending id), matching the
    historical full-sort behaviour exactly.
    """
    relevant = np.nonzero(scores >= _MIN_SCORE)[0]
    if relevant.size == 0 or k <= 0:
        return []
    rel_scores = scores[relevant]
    if rel_scores.size > k:
        cut = np.partition(rel_scores, rel_scores.size - k)[rel_scores.size - k]
        candidates = relevant[rel_scores >= cut]
    else:
        candidates = relevant
    ordered = sorted(candidates.tolist(), key=lambda i: (-float(scores[i]), i))
    return ordered[:k]


def _like_pattern(text: str) -> str:
    """Build a contains-pattern for LIKE with %, _ and backslash escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def remember(text: str, kind: str = "fact") -> bool:
    """Store *text* with its embedding. Returns False on any failure (never raises)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    try:
        vector = np.asarray(embed_text(cleaned), dtype=np.float32)
        blob = vector.tobytes()
        created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _lock:
            cur = _get_conn().execute(
                "INSERT INTO memories(text, kind, embedding, created_at)"
                " VALUES(?, ?, ?, ?)",
                (cleaned, kind, blob, created),
            )
            _get_conn().commit()
            _append_to_cache_locked(int(cur.lastrowid), cleaned, kind, created, vector)
        return True
    except Exception as e:
        logger.warning("Semantic remember failed: %s", e)
        return False


def recall(query: str, k: int = 3) -> list[str]:
    """Return up to *k* stored texts ranked by cosine similarity to *query*."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        query_vec = np.asarray(embed_text(q), dtype=np.float32)
        with _lock:
            snapshot = _ensure_fresh_cache_locked()
        if snapshot is None or snapshot.matrix.shape[0] == 0:
            return []
        scores = _score_snapshot(snapshot, query_vec)
        order = _top_k_indices(scores, k)
        return [f"[{snapshot.kinds[i]}] {snapshot.texts[i]}" for i in order]
    except Exception as e:
        logger.warning("Semantic recall failed: %s", e)
        return []


def list_memories(query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    """List rows newest-first, optionally filtered by case-insensitive substring.

    Each dict is {"id": int, "text": str, "kind": str, "created_at": str}.
    Reads never need embeddings, so listing works even when embedding fails.
    """
    q = (query or "").strip()
    try:
        lim = max(1, min(_LIST_LIMIT_MAX, int(limit)))
        off = max(0, int(offset))
        sql = "SELECT id, text, kind, created_at FROM memories"
        params: list[object] = []
        if q:
            sql += " WHERE text LIKE ? ESCAPE '\\'"
            params.append(_like_pattern(q))
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([lim, off])
        with _lock:
            _ensure_fresh_cache_locked()  # keeps the vector cache staleness-checked
            rows = _get_conn().execute(sql, params).fetchall()
        return [{"id": r[0], "text": r[1], "kind": r[2], "created_at": r[3]} for r in rows]
    except Exception as e:
        logger.warning("Semantic list failed: %s", e)
        return []


def count_memories(query: str = "") -> int:
    """Number of stored memories matching the optional substring filter."""
    q = (query or "").strip()
    try:
        sql = "SELECT COUNT(*) FROM memories"
        params: list[object] = []
        if q:
            sql += " WHERE text LIKE ? ESCAPE '\\'"
            params.append(_like_pattern(q))
        with _lock:
            _ensure_fresh_cache_locked()
            total = _get_conn().execute(sql, params).fetchone()[0]
        return int(total)
    except Exception as e:
        logger.warning("Semantic count failed: %s", e)
        return 0


def delete_memory(memory_id: int) -> bool:
    """Delete one memory row. False when absent or anything fails (never raises)."""
    try:
        mid = int(memory_id)
    except (TypeError, ValueError):
        logger.warning("Semantic delete rejected id: %r", memory_id)
        return False
    try:
        with _lock:
            cur = _get_conn().execute("DELETE FROM memories WHERE id = ?", (mid,))
            _get_conn().commit()
            removed = cur.rowcount > 0
            if removed:
                _drop_from_cache_locked(mid)
        if not removed:
            logger.warning("Semantic delete missed id %s", mid)
        return removed
    except Exception as e:
        logger.warning("Semantic delete failed: %s", e)
        return False


def update_text(memory_id: int, text: str) -> bool:
    """Replace a row's text and re-embed it.

    Returns False (leaving row AND cache untouched) on empty text, unknown id,
    or embed failure. Identical stripped text short-circuits True.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    try:
        mid = int(memory_id)
    except (TypeError, ValueError):
        logger.warning("Semantic update rejected id: %r", memory_id)
        return False
    try:
        with _lock:
            row = _get_conn().execute(
                "SELECT text FROM memories WHERE id = ?", (mid,)
            ).fetchone()
        if row is None:
            logger.warning("Semantic update missed id %s", mid)
            return False
        if row[0].strip() == cleaned:
            return True
        vector = np.asarray(embed_text(cleaned), dtype=np.float32)
        with _lock:
            cur = _get_conn().execute(
                "UPDATE memories SET text = ?, embedding = ? WHERE id = ?",
                (cleaned, vector.tobytes(), mid),
            )
            _get_conn().commit()
            if cur.rowcount == 0:
                return False
            _replace_in_cache_locked(mid, cleaned, vector)
        return True
    except Exception as e:
        logger.warning("Semantic update failed: %s", e)
        return False


def format_recall_for_prompt(query: str, k: int = 3) -> str:
    """Format recall results as a prompt block, or "" when nothing matched."""
    results = recall(query, k=k)
    if not results:
        return ""
    lines = [_PROMPT_HEADER]
    lines.extend(f"- {item}" for item in results)
    return "\n".join(lines)
