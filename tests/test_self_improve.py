from __future__ import annotations

import pytest

from actions import self_improve as si


@pytest.fixture
def backlog_file(tmp_path, monkeypatch):
    path = tmp_path / "self_improvements.md"
    path.write_text(
        """## Improvements

### P2 — voice
- [x] **Done item** — already shipped
- [ ] **Fix prompt** — update core/prompt.txt routing

### P3 — polish
- [ ] **Migrate genai** — switch to google.genai
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(si, "BACKLOG_PATH", path)
    return path


def test_parse_backlog(backlog_file):
    items = si._load_items()
    assert len(items) == 3
    assert items[0].done
    assert not items[1].done
    assert items[1].title == "Fix prompt"


def test_list_pending(backlog_file):
    out = si.self_improve({"action": "list"})
    assert "Fix prompt" in out
    assert "Migrate genai" in out
    assert "Done item" not in out


def test_mark_done(backlog_file):
    msg = si.self_improve({"action": "mark_done", "title": "Fix prompt"})
    assert "Marked done" in msg
    items = si._load_items()
    fix = next(it for it in items if it.title == "Fix prompt")
    assert fix.done


def test_run_next_auto_mark_done_on_verify_ok(monkeypatch, backlog_file):
    monkeypatch.setattr(
        "actions.coding_workspace.coding_workspace",
        lambda params, **kwargs: "VERIFY_OK\n\nall passed",
    )
    out = si.self_improve({"action": "run_next"})
    assert "Marked done" in out
    items = si._load_items()
    fix = next(it for it in items if it.title == "Fix prompt")
    assert fix.done


def test_run_next_calls_coding(monkeypatch, backlog_file):
    called = {}

    def fake_coding_workspace(params, **kwargs):
        called["params"] = params
        return "coding result"

    monkeypatch.setattr(
        "actions.coding_workspace.coding_workspace",
        fake_coding_workspace,
    )
    out = si.self_improve({"action": "run_next"})
    assert "Fix prompt" in out
    assert called["params"]["action"] == "task"
    assert "Fix prompt" in called["params"]["goal"]
