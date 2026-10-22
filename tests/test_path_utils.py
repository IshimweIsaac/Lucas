"""Tests for canonical path resolution."""

from __future__ import annotations

from pathlib import Path


from core.path_utils import normalize_tool_paths, resolve_user_path


def test_shortcut_lucas():
    res = resolve_user_path("lucas")
    assert res.ok
    assert Path(res.path) == Path(__file__).resolve().parent.parent


def test_shortcut_documents_exists():
    res = resolve_user_path("documents", must_be_dir=True)
    assert res.ok
    assert Path(res.path).is_dir()


def test_wrong_case_fixed_if_unique(tmp_path, monkeypatch):
    real = tmp_path / "MyProject"
    real.mkdir()
    wrong = tmp_path / "myproject"
    res = resolve_user_path(str(wrong), must_exist=True)
    assert res.ok
    assert Path(res.path).name == "MyProject"


def test_lowercase_folder_kept_when_exists(tmp_path):
    low = tmp_path / "myapp"
    low.mkdir()
    res = resolve_user_path(str(low), must_exist=True)
    assert res.ok
    assert Path(res.path).name == "myapp"
    assert not res.corrected


def test_nonexistent_suggests():
    res = resolve_user_path(str(Path.home() / "Documents" / "NoSuchProject_xyz_123"), must_exist=True)
    assert not res.ok
    assert "does not exist" in res.message.lower()


def test_normalize_blocks_bad_file_read():
    args, block = normalize_tool_paths(
        "file_controller",
        {"action": "read", "path": "/tmp/definitely_not_a_lucas_file_99999.txt"},
    )
    assert block is not None
    assert "does not exist" in block.lower()


def test_normalize_fixes_shortcut():
    args, block = normalize_tool_paths(
        "file_controller",
        {"action": "list", "path": "documents"},
    )
    assert block is None
    assert Path(args["path"]).is_dir()


def test_normalize_allows_create_folder_new_path(tmp_path):
    new_dir = tmp_path / "calling_guests"
    args, block = normalize_tool_paths(
        "file_controller",
        {"action": "create_folder", "path": str(new_dir)},
    )
    assert block is None
    assert args["path"] == str(new_dir.resolve())


def test_normalize_allows_copy_destination_new_file(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hi", encoding="utf-8")
    dst = tmp_path / "out" / "b.txt"
    args, block = normalize_tool_paths(
        "file_controller",
        {"action": "copy", "path": str(src), "destination": str(dst)},
    )
    assert block is None
    assert args["destination"] == str(dst.resolve())


def test_normalize_blocks_copy_missing_source(tmp_path):
    src = tmp_path / "missing.csv"
    dst = tmp_path / "out.csv"
    args, block = normalize_tool_paths(
        "file_controller",
        {"action": "copy", "path": str(src), "destination": str(dst)},
    )
    assert block is not None
    assert "does not exist" in block.lower()
