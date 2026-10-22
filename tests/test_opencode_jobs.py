"""Tests for core/opencode/opencode_jobs.py — GC, purge, cap, foreground repair.

All tests patch ``load_state``/``save_state`` so the real
``memory/opencode_live.json`` is never touched.
"""

from __future__ import annotations

import time

import pytest

from core.opencode import opencode_jobs as ocj


def _job(token: str, *, phase: str = "running", started_at: float, updated_at: float | None = None) -> dict:
    return {
        "token": token,
        "goal": "goal-" + token,
        "phase": phase,
        "started_at": started_at,
        "updated_at": updated_at if updated_at is not None else started_at,
    }


def _make_state(jobs: dict, *, fg: str = "") -> dict:
    return {
        "server": {},
        "active_session_id": "",
        "active_workspace": "",
        "pending_jobs": jobs,
        "foreground_job_token": fg,
    }


@pytest.fixture()
def fake_state(monkeypatch):
    """State holder patched into opencode_jobs load_state/save_state."""
    holder: dict = {"state": _make_state({})}

    def _load() -> dict:
        return dict(holder["state"])

    def _save(state: dict) -> None:
        holder["state"] = dict(state)

    monkeypatch.setattr(ocj, "load_state", _load)
    monkeypatch.setattr(ocj, "save_state", _save)
    return holder


class TestPurgeZombies:
    def test_purge_removes_stale_running_job(self, fake_state):
        now = time.time()
        fresh = _job("fresh", started_at=now - 10, updated_at=now - 2)
        stale = _job("stale", started_at=now - 7200, updated_at=now - 7200)
        fake_state["state"] = _make_state({"fresh": fresh, "stale": stale})

        stats = ocj.gc()

        assert stats["purged"] == 1
        remaining = ocj.list_jobs()
        assert [j["token"] for j in remaining] == ["fresh"]

    def test_fresh_running_job_kept(self, fake_state):
        now = time.time()
        fresh = _job("fresh", started_at=now - 30, updated_at=now - 1)
        fake_state["state"] = _make_state({"fresh": fresh})
        stats = ocj.gc()
        assert stats["purged"] == 0
        assert [j["token"] for j in ocj.list_jobs()] == ["fresh"]

    def test_finished_jobs_never_purged_as_zombies(self, fake_state):
        now = time.time()
        done = _job("done", phase="complete", started_at=now - 999999, updated_at=now - 999999)
        fake_state["state"] = _make_state({"done": done})
        stats = ocj.gc()
        assert stats["purged"] == 0
        assert [j["token"] for j in ocj.list_jobs()] == ["done"]


class TestForegroundRepair:
    def test_foreground_repaired_to_fresh_running(self, fake_state):
        now = time.time()
        fresh = _job("fresh", started_at=now - 5, updated_at=now - 2)
        stale = _job("stale", started_at=now - 7200, updated_at=now - 7200)
        fake_state["state"] = _make_state({"fresh": fresh, "stale": stale}, fg="stale")
        ocj.gc()
        assert ocj.foreground_token() == "fresh"

    def test_foreground_cleared_when_no_running(self, fake_state):
        now = time.time()
        stale = _job("stale", started_at=now - 7200, updated_at=now - 7200)
        fake_state["state"] = _make_state({"stale": stale}, fg="stale")
        ocj.gc()
        assert ocj.foreground_token() == ""

    def test_foreground_kept_when_valid(self, fake_state):
        now = time.time()
        fresh = _job("fresh", started_at=now - 10, updated_at=now - 1)
        fake_state["state"] = _make_state({"fresh": fresh}, fg="fresh")
        ocj.gc()
        assert ocj.foreground_token() == "fresh"


class TestCap:
    def test_cap_limits_retained_history(self, fake_state):
        now = time.time()
        jobs = {}
        for i in range(ocj.MAX_RETAINED_JOBS + 30):
            jobs[f"done_{i}"] = {
                "token": f"done_{i}",
                "phase": "complete",
                "started_at": now - 1000 + i,
                "updated_at": now - 1000 + i,
            }
        jobs["fresh"] = _job("fresh", started_at=now - 10, updated_at=now - 1)
        fake_state["state"] = _make_state(jobs)
        stats = ocj.gc()
        assert stats["capped"] == 30
        remaining = [j["token"] for j in ocj.list_jobs()]
        assert "fresh" in remaining
        assert len([t for t in remaining if t.startswith("done")]) == ocj.MAX_RETAINED_JOBS

    def test_no_cap_when_under_limit(self, fake_state):
        now = time.time()
        jobs = {}
        for i in range(10):
            jobs[f"done_{i}"] = {
                "token": f"done_{i}",
                "phase": "complete",
                "started_at": now - 100 - i,
                "updated_at": now - 100 - i,
            }
        fake_state["state"] = _make_state(jobs)
        stats = ocj.gc()
        assert stats["capped"] == 0
        assert len(ocj.list_jobs()) == 10


class TestViewAndLifecycle:
    def test_purge_view_ignores_zombies_on_read(self, fake_state):
        now = time.time()
        stale = _job("stale", started_at=now - 7200, updated_at=now - 7200)
        fake_state["state"] = _make_state({"stale": stale})
        # Without calling gc(), a read path must NOT report the zombie.
        assert ocj.list_jobs(running_only=True) == []

    def test_register_sets_updated_at(self, fake_state):
        token = ocj.register({"goal": "hello"})
        job = ocj.get(token)
        assert "updated_at" in job
        assert job["updated_at"] > time.time() - 10

    def test_gc_idempotent(self, fake_state):
        now = time.time()
        fresh = _job("fresh", started_at=now - 10, updated_at=now - 1)
        fake_state["state"] = _make_state({"fresh": fresh})
        assert ocj.gc()["purged"] == 0
        assert ocj.gc()["purged"] == 0

    def test_update_touches_updated_at(self, fake_state):
        before = time.time()
        token = ocj.register({"goal": "x"})
        ocj.update(token, phase="running")
        job = ocj.get(token)
        assert job["updated_at"] >= before

    def test_stale_purge_returns_count(self, fake_state):
        now = time.time()
        stale = _job("stale", started_at=now - 7200, updated_at=now - 7200)
        fake_state["state"] = _make_state({"stale": stale})
        assert ocj.stale_purge() == 1
