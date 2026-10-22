"""Tests for patch_lines safety guards."""

from __future__ import annotations

from pathlib import Path

from actions import coding_workspace as cw


def test_patch_lines_rejects_whole_file_wipe(tmp_path: Path):
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir(parents=True)
    lines = ["line %d\n" % i for i in range(1, 101)]
    target.write_text("".join(lines), encoding="utf-8")

    msg = cw._apply_patch_lines(
        tmp_path,
        "pkg/mod.py",
        1,
        100,
        "tiny",
    )
    assert "Patch rejected" in msg
    assert target.read_text(encoding="utf-8").startswith("line 1")
