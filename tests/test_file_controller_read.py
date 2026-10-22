"""Tests for file_controller chunked read."""

from __future__ import annotations

from pathlib import Path

import actions.file_controller as fc
from actions.file_controller import read_file


def test_read_file_line_range(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_SAFE_ROOTS", [Path(tmp_path)])
    f = tmp_path / "sample.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 101)), encoding="utf-8")

    out = read_file(str(f), start_line=1, end_line=100)
    assert "lines 1-100 of 100" in out
    assert "line 1" in out
    assert "line 100" in out
    assert "More content" not in out


def test_read_file_pagination_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_SAFE_ROOTS", [Path(tmp_path)])
    f = tmp_path / "long.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 251)), encoding="utf-8")

    out = read_file(str(f), start_line=1)
    assert "lines 1-200 of 250" in out
    assert "start_line=201" in out
