"""Registry for parallel OpenCode background jobs."""

from __future__ import annotations

import threading
import time
from typing import Any

from core.opencode.opencode_server import load_state, save_state

MAX_PARALLEL_JOBS = 8
_RUNNING_PHASES = frozenset({"starting", "running", "active"})
# A job stuck in a running phase without any update for this long is a zombie.
_IDLE_STALENESS_SEC = 3600.0
# Keep at most this many finished jobs in retained history (running jobs always kept).
MAX_RETAINED_JOBS = 100

_lock = threading.Lock()
_active_tokens: set[str] = set()


def _is_zombie(job: dict[str, Any]) -> bool:
    """Return True when a job claims to be running but has been idle too long.

    A live background worker refreshes ``updated_at`` on every progress event,
    so a job stuck in a running phase without an update for more than
    ``_IDLE_STALENESS_SEC`` seconds is not truly active (crash / stale test run).
    Jobs tracked in the in-process ``_active_tokens`` set are never zombies —
    a worker thread may legitimately wait long on a session without events.
    """
    phase = str(job.get("phase") or "")
    if phase not in _RUNNING_PHASES:
        return False
    if str(job.get("token") or "") in _active_tokens:
        return False
    updated = float(job.get("updated_at") or job.get("started_at") or 0)
    return bool(updated) and (time.time() - updated) > _IDLE_STALENESS_SEC


def _purged_view(jobs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return a filtered copy with stale zombie jobs dropped (no disk write)."""
    return {t: j for t, j in jobs.items() if not _is_zombie(j)}


def _empty_jobs() -> dict[str, dict[str, Any]]:
    raw = load_state().get("pending_jobs") or {}
    if isinstance(raw, dict):
        base = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
    else:
        base = {}
    # Purge zombies on every read so list/status/count never report dead jobs.
    return _purged_view(base)


def _repair_foreground(state: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> str:
    """Point foreground_job_token at a live running job (or clear it)."""
    fg = (state.get("foreground_job_token") or "").strip()
    if fg and fg in jobs and str(jobs[fg].get("phase") or "") in _RUNNING_PHASES:
        return fg
    running = [
        (float(j.get("started_at") or 0), t)
        for t, j in jobs.items()
        if str(j.get("phase") or "") in _RUNNING_PHASES
    ]
    new_fg = max(running)[1] if running else ""
    state["foreground_job_token"] = new_fg
    return new_fg


def _persist(jobs: dict[str, dict[str, Any]]) -> None:
    state = load_state()
    state["pending_jobs"] = jobs
    running = [j for j in jobs.values() if str(j.get("phase") or "") in _RUNNING_PHASES]
    if not running:
        state.pop("pending_job", None)
    else:
        fg = _repair_foreground(state, jobs)
        if fg and fg in jobs:
            state["pending_job"] = jobs[fg]
        else:
            state["pending_job"] = running[-1]
    _repair_foreground(state, jobs)
    save_state(state)


def register(job: dict[str, Any]) -> str:
    token = str(job.get("token") or time.time_ns())
    data = dict(job)
    data["token"] = token
    data.setdefault("started_at", time.time())
    data.setdefault("phase", "starting")
    data.setdefault("updated_at", time.time())
    with _lock:
        jobs = _empty_jobs()
        jobs[token] = data
        _active_tokens.add(token)
        _persist(jobs)
        state = load_state()
        state["foreground_job_token"] = token
        save_state(state)
    return token


def update(job_token: str, **fields: Any) -> None:
    job_token = (job_token or "").strip()
    if not job_token:
        return
    fields.pop("token", None)
    fields["updated_at"] = time.time()
    with _lock:
        jobs = _empty_jobs()
        job = jobs.get(job_token)
        if not job:
            job = {"token": job_token, "started_at": time.time(), "phase": "starting"}
            jobs[job_token] = job
        job.update(fields)
        jobs[job_token] = job
        _persist(jobs)


def finish(token: str, *, phase: str = "complete", error: str = "") -> None:
    token = (token or "").strip()
    if not token:
        return
    with _lock:
        jobs = _empty_jobs()
        job = jobs.pop(token, None)
        _active_tokens.discard(token)
        if job:
            job["phase"] = phase
            if error:
                job["error"] = error
            job["finished_at"] = time.time()
            # Retain finished/cancelled jobs as history; only gc()/cap trims them.
            jobs[token] = job
        _persist(jobs)


def remove(token: str) -> None:
    finish(token, phase="cancelled")


def get(token: str) -> dict[str, Any]:
    token = (token or "").strip()
    with _lock:
        return dict(_empty_jobs().get(token) or {})


def resolve_token(ref: str) -> str:
    """Match full token or unique prefix."""
    ref = (ref or "").strip()
    if not ref:
        return ""
    with _lock:
        jobs = _empty_jobs()
        if ref in jobs:
            return ref
        matches = [t for t in jobs if t.startswith(ref)]
        if len(matches) == 1:
            return matches[0]
        active = [t for t in _active_tokens if t.startswith(ref)]
        if len(active) == 1:
            return active[0]
        return ref if ref in _active_tokens else ""


def list_jobs(*, running_only: bool = False) -> list[dict[str, Any]]:
    with _lock:
        jobs = list(_empty_jobs().values())
        active = set(_active_tokens)
    out = []
    for job in jobs:
        token = str(job.get("token") or "")
        phase = str(job.get("phase") or "")
        is_run = phase in _RUNNING_PHASES or token in active
        if running_only and not is_run:
            continue
        row = dict(job)
        row["running"] = is_run
        out.append(row)
    out.sort(key=lambda j: float(j.get("started_at") or 0))
    return out


def count_running() -> int:
    with _lock:
        jobs = _empty_jobs()
        active = set(_active_tokens)
    n = 0
    seen: set[str] = set()
    for token in active:
        seen.add(token)
        n += 1
    for token, job in jobs.items():
        if token in seen:
            continue
        if str(job.get("phase") or "") in _RUNNING_PHASES:
            n += 1
    return n


def is_token_active(token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    with _lock:
        if token in _active_tokens:
            return True
        job = _empty_jobs().get(token) or {}
        return str(job.get("phase") or "") in _RUNNING_PHASES


def mark_active(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    with _lock:
        _active_tokens.add(token)


def mark_inactive(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    with _lock:
        _active_tokens.discard(token)


def foreground_token() -> str:
    return str(load_state().get("foreground_job_token") or "").strip()


def set_foreground(token: str) -> None:
    token = (token or "").strip()
    state = load_state()
    state["foreground_job_token"] = token
    save_state(state)


def gc() -> dict:
    """Garbage-collect the job registry.

    Purges stale zombie jobs stuck in running phases, caps retained finished
    history at ``MAX_RETAINED_JOBS``, and repairs ``foreground_job_token`` so
    follow-up targets a live session (never a stale test job).

    Returns:
        Stats dict: purged, capped, foreground_repaired, foreground_token, retained.
    """
    with _lock:
        state = load_state()
        raw = state.get("pending_jobs") or {}
        if not isinstance(raw, dict):
            raw = {}
        raw = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
        zombies = [t for t, j in raw.items() if _is_zombie(j)]
        for t in zombies:
            raw.pop(t, None)
            _active_tokens.discard(t)

        running = [
            (t, j) for t, j in raw.items()
            if str(j.get("phase") or "") in _RUNNING_PHASES
        ]
        finished = [
            (t, j) for t, j in raw.items()
            if str(j.get("phase") or "") not in _RUNNING_PHASES
        ]
        capped = max(0, len(finished) - MAX_RETAINED_JOBS)
        finished.sort(key=lambda tj: float(tj[1].get("started_at") or 0), reverse=True)
        dropped = finished[MAX_RETAINED_JOBS:]
        for t, _j in dropped:
            raw.pop(t, None)

        state["pending_jobs"] = raw
        old_fg = (state.get("foreground_job_token") or "").strip()
        new_fg = _repair_foreground(state, raw)
        if not running:
            state.pop("pending_job", None)
        save_state(state)

    return {
        "purged": len(zombies),
        "capped": capped,
        "foreground_repaired": bool(old_fg) and old_fg != new_fg,
        "foreground_token": new_fg,
        "retained": len(raw),
    }


def stale_purge() -> int:
    """Convenience wrapper — returns how many zombie jobs were purged."""
    return int(gc().get("purged") or 0)


def pending_job() -> dict[str, Any]:
    fg = foreground_token()
    if fg:
        job = get(fg)
        if job:
            return job
    jobs = list_jobs(running_only=True)
    return jobs[-1] if jobs else {}


def is_running() -> bool:
    return count_running() > 0


def clear_all() -> list[str]:
    with _lock:
        tokens = list(_active_tokens) + [
            t
            for t, j in _empty_jobs().items()
            if str(j.get("phase") or "") in _RUNNING_PHASES
        ]
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out
