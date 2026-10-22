from __future__ import annotations

import json

import pytest

from memory import session_brief as sb


@pytest.fixture(autouse=True)
def isolated_brief(tmp_path, monkeypatch):
    path = tmp_path / "session_brief.json"
    monkeypatch.setattr(sb, "BRIEF_PATH", path)
    yield
    if path.exists():
        path.unlink()


def test_add_and_format():
    sb.add_bullet("Workspace set to Lucas")
    sb.set_topic("coding challenge")
    out = sb.format_for_prompt()
    assert "SESSION BRIEF" in out
    assert "coding challenge" in out
    assert "Workspace set to Lucas" in out


def test_clear_on_phrase():
    sb.add_bullet("old fact")
    sb.note_turn("let's start over please", "")
    data = sb.load_brief()
    assert "old fact" not in data.get("bullets", [])


def test_trim_old_bullets():
    for i in range(30):
        sb.add_bullet(f"bullet {i}")
    data = sb.load_brief()
    assert len(data["bullets"]) <= sb.MAX_BULLETS


def test_note_tool_skips_save_memory():
    sb.note_tool("save_memory", "ok", {"category": "notes"})
    assert sb.load_brief().get("bullets") == []


def test_lumina_filtered_unless_user_said_it():
    sb.clear_brief()
    sb.note_turn("fix Lucas tests", "working in Lumina repo now")
    data = sb.load_brief()
    bullets = " ".join(data.get("bullets", []))
    assert "Lumina" not in bullets
    assert "the project" in bullets.lower() or "Lucas" in bullets


def test_pin_coding_workspace():
    sb.pin_coding_workspace("/tmp/lucas-test-repo")
    out = sb.format_for_prompt()
    assert "Active coding workspace:" in out
    assert "lucas-test-repo" in out


def test_persists_to_disk(tmp_path, monkeypatch):
    path = tmp_path / "session_brief.json"
    monkeypatch.setattr(sb, "BRIEF_PATH", path)
    sb.add_bullet("persisted")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "persisted" in data["bullets"]
