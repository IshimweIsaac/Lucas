"""Tests for core.sway_control — swaymsg wrapper (hermetic via monkeypatch)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from core import sway_control as sc


@dataclass
class _FakeResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _patch_run(monkeypatch, result: _FakeResult, captured: list) -> None:
    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(sc, "swaymsg_available", lambda: True)


def test_swaymsg_available_true(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/swaymsg")
    assert sc.swaymsg_available() is True


def test_swaymsg_available_false(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert sc.swaymsg_available() is False


def test_switch_workspace_happy_path(monkeypatch):
    captured: list[list[str]] = []
    _patch_run(monkeypatch, _FakeResult(returncode=0), captured)
    result = sc.switch_workspace(3)
    assert captured == [["swaymsg", "workspace", "number", "3"]]
    assert "3" in result
    assert "Switched" in result


def test_switch_workspace_failure_returns_error(monkeypatch):
    captured: list[list[str]] = []
    _patch_run(monkeypatch, _FakeResult(returncode=1, stderr="nope"), captured)
    result = sc.switch_workspace(4)
    assert "Failed" in result
    assert "4" in result
    assert "nope" in result


def test_switch_workspace_invalid_number_no_subprocess(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("subprocess must not run for invalid numbers")

    monkeypatch.setattr(subprocess, "run", boom)
    for bad in (0, -3, "abc", 1.5):
        result = sc.switch_workspace(bad)
        assert "Invalid" in result


def test_switch_workspace_missing_swaymsg_safe_fail(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("subprocess must not run when swaymsg missing")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(sc, "swaymsg_available", lambda: False)
    result = sc.switch_workspace(5)
    assert "swaymsg" in result


def test_list_workspaces_parsing(monkeypatch):
    payload = json.dumps([
        {"name": "1:web", "num": 1, "focused": True},
        {"name": "2:code", "num": 2, "focused": False},
    ])
    captured: list[list[str]] = []
    _patch_run(monkeypatch, _FakeResult(returncode=0, stdout=payload), captured)
    result = sc.list_workspaces()
    assert captured == [["swaymsg", "-t", "get_workspaces"]]
    assert "1:web" in result
    assert "2:code" in result
    assert "focused" in result


def test_list_workspaces_empty(monkeypatch):
    _patch_run(monkeypatch, _FakeResult(returncode=0, stdout="[]"), [])
    assert "No workspaces" in sc.list_workspaces()


def test_list_workspaces_invalid_json(monkeypatch):
    _patch_run(monkeypatch, _FakeResult(returncode=0, stdout="not json"), [])
    assert "Could not parse" in sc.list_workspaces()


def test_list_workspaces_missing_swaymsg(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("subprocess must not run when swaymsg missing")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(sc, "swaymsg_available", lambda: False)
    assert "swaymsg" in sc.list_workspaces()