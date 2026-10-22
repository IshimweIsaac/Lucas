"""Tests for Gemini SearchAgent (mocked API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.key_manager import KeyManager
from agent.search_agent import SearchAgent


@pytest.fixture
def agent_keys_file(tmp_path: Path) -> Path:
    path = tmp_path / "agent_keys.json"
    path.write_text(
        json.dumps({"gemini": ["key-a", "key-b"], "groq": []}),
        encoding="utf-8",
    )
    return path


def test_search_agent_uses_rotated_key(agent_keys_file, monkeypatch):
    monkeypatch.setattr("agent.key_manager._KEYS_FILE", agent_keys_file)
    monkeypatch.setattr("agent.key_manager._instance", None)
    km = KeyManager(keys_file=agent_keys_file)
    monkeypatch.setattr("agent.key_manager.get_key_manager", lambda: km)

    calls: list[str] = []

    def fake_generate(model, contents, *, provider="gemini", system_instruction=None):
        calls.append(km.get_key(provider))
        return "Answer: use pytest for verify."

    monkeypatch.setattr(
        "memory.gemini_text.generate_text_with_agent_key",
        fake_generate,
    )
    monkeypatch.setattr(
        "agent.search_agent.generate_text_with_agent_key",
        fake_generate,
    )

    r1 = SearchAgent(model="gemini-3.1-flash-lite").search("how to test FastAPI", goal="add tests")
    _   = SearchAgent(model="gemini-3.1-flash-lite").search("second query")

    assert r1.ok
    assert "pytest" in r1.answer
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_search_agent_requires_keys(tmp_path, monkeypatch):
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("agent.key_manager._KEYS_FILE", empty)
    monkeypatch.setattr("agent.key_manager._instance", None)
    monkeypatch.setattr(
        "memory.config_manager.get_gemini_key",
        lambda: "",
    )

    with pytest.raises(RuntimeError, match="agent_keys"):
        SearchAgent().search("test")
