"""Tests for the pid-file helpers and single-instance guard in core.alert_delivery."""

from __future__ import annotations

import os
import signal
from unittest.mock import MagicMock

import pytest

from core import alert_delivery as ad


@pytest.fixture
def pid_file(tmp_path, monkeypatch):
    f = tmp_path / "lucas.pid"
    monkeypatch.setattr(ad, "PID_FILE", f)
    return f


def _no_pgrep(cmd, **kwargs):
    return MagicMock(returncode=1, stdout="", stderr="")


def test_lucas_is_running_live_pid_detected(pid_file, monkeypatch):
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(ad.os, "kill", lambda *a, **k: None)
    assert ad.lucas_is_running() is True
    assert pid_file.exists() is True


def test_lucas_is_running_stale_pid_unlinked(pid_file, monkeypatch):
    pid_file.write_text("999999", encoding="utf-8")

    def fake_kill(pid, sig):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(ad.os, "kill", fake_kill)
    monkeypatch.setattr(ad.subprocess, "run", _no_pgrep)
    assert ad.lucas_is_running() is False
    assert pid_file.exists() is False


def test_lucas_is_running_pgrep_fallback(pid_file, monkeypatch):
    monkeypatch.setattr(
        ad.subprocess,
        "run",
        lambda *a, **k: MagicMock(returncode=0, stdout="1234\n", stderr=""),
    )
    assert ad.lucas_is_running() is True


def test_enforce_single_instance_kills_live_and_clears(pid_file, monkeypatch):
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.delenv("LUCAS_REFUSE_SECOND", raising=False)
    monkeypatch.setattr(ad.os, "kill", lambda *a, **k: None)
    monkeypatch.setattr(ad.subprocess, "run", _no_pgrep)
    killed = []
    monkeypatch.setattr(ad, "_kill_pid", lambda pid: killed.append(pid) or True)
    ad.enforce_single_instance()
    assert killed == [4242]
    assert pid_file.exists() is False


def test_enforce_single_instance_refuse_exits(pid_file, monkeypatch, capsys):
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setenv("LUCAS_REFUSE_SECOND", "1")
    monkeypatch.setattr(ad.os, "kill", lambda *a, **k: None)
    monkeypatch.setattr(ad.subprocess, "run", _no_pgrep)
    killed = []
    monkeypatch.setattr(ad, "_kill_pid", lambda pid: killed.append(pid) or True)
    with pytest.raises(SystemExit) as exc:
        ad.enforce_single_instance()
    assert exc.value.code == 1
    assert killed == []
    assert "Lucas already running (PID 4242)" in capsys.readouterr().out


def test_enforce_single_instance_stale_proceeds(pid_file, monkeypatch):
    pid_file.write_text("999999", encoding="utf-8")

    def fake_kill(pid, sig):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(ad.os, "kill", fake_kill)
    monkeypatch.setattr(ad.subprocess, "run", _no_pgrep)
    killed = []
    monkeypatch.setattr(ad, "_kill_pid", lambda pid: killed.append(pid) or True)
    ad.enforce_single_instance()  # stale pid -> no kill, no exception
    assert killed == []
    assert pid_file.exists() is False


def test_kill_pid_escalates_to_sigkill(monkeypatch):
    calls = []

    def fake_kill(pid, sig):
        calls.append(sig)
        return None

    monkeypatch.setattr(ad.os, "kill", fake_kill)
    monkeypatch.setattr(ad.time, "sleep", lambda s: None)
    assert ad._kill_pid(4242) is True
    assert signal.SIGTERM in calls
    assert signal.SIGKILL in calls


def test_candidate_pids_excludes_self_and_dedupes(pid_file, monkeypatch):
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.setattr(
        ad.subprocess,
        "run",
        lambda *a, **k: MagicMock(
            returncode=0, stdout=f"{os.getpid()}\n1111\n", stderr=""
        ),
    )
    pids = ad._candidate_pids()
    assert os.getpid() not in pids
    assert 1111 in pids
