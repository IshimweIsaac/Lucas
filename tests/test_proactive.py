"""Tests for the proactive companion subsystem (SPEC sections 6-8).

Follows the repo pattern: monkeypatch module-level file constants to tmp_path,
mock the Gemini call, and use asyncio.run for the async run() entry point
(pytest-asyncio is in STRICT mode and the repo uses asyncio.run).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from actions.proactive import proactive as proactive_tool
from core import calendar_store
from core import proactive
from core.proactive import config
from core.proactive import curator
from core.proactive import engagement_store
from core.proactive import governor
from core.proactive import persona
from core.proactive import project_research
from core.proactive import relevance
from core.proactive import research_ideas_store
from core.proactive import scanner
from memory import semantic_memory


@pytest.fixture
def store_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "proactive_config.json")
    monkeypatch.setattr(
        engagement_store, "ENGAGEMENT_FILE", tmp_path / "proactive_engagement.json"
    )
    monkeypatch.setattr(
        research_ideas_store, "IDEAS_FILE", tmp_path / "research_ideas.json"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


def test_persona_tokens():
    text = persona.persona_block()
    assert "sir" in text
    assert "Never be cocky" in text
    assert "config/" in text
    assert "may I share" in text


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_defaults_created_on_first_load(store_file):
    cfg = config.load_config()
    assert config.CONFIG_FILE.exists()
    assert cfg["budget"]["max_web_searches_per_day"] == 12
    assert cfg["quiet_start"] == "22:00"
    assert cfg["quiet_end"] == "06:00"
    assert cfg["thresholds"]["relevance_min"] == 0.6


def test_config_roundtrip(store_file):
    cfg = config.load_config()
    cfg["pacing_minutes"] = 45
    config.save_config(cfg)
    assert config.load_config()["pacing_minutes"] == 45


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------


def test_in_quiet_hours(store_file):
    cfg = config.load_config()
    assert governor.in_quiet_hours(cfg, now=datetime(2026, 8, 8, 23, 0)) is True
    assert governor.in_quiet_hours(cfg, now=datetime(2026, 8, 8, 12, 0)) is False
    assert governor.in_quiet_hours(cfg, now=datetime(2026, 8, 8, 5, 0)) is True
    assert governor.in_quiet_hours(cfg, now=datetime(2026, 8, 8, 6, 0)) is False


def test_dnd_active(store_file):
    cfg = config.load_config()
    cfg["dnd_until_iso"] = "2099-01-01T00:00:00"
    assert governor.dnd_active(cfg, now=datetime(2026, 8, 8, 12, 0)) is True
    cfg["dnd_until_iso"] = "2020-01-01T00:00:00"
    assert governor.dnd_active(cfg, now=datetime(2026, 8, 8, 12, 0)) is False
    cfg["dnd_enabled"] = True
    assert governor.dnd_active(cfg, now=datetime(2026, 8, 8, 12, 0)) is True


def test_can_work_budget_exhausted(store_file):
    cfg = config.load_config()
    counters = {"date": "2026-08-08", "llm": 6, "web": 0, "reads": 0, "speech": 0}
    ok, reason = governor.can_work(
        cfg, counters=counters, now=datetime(2026, 8, 8, 12, 0)
    )
    assert ok is False
    assert reason == "budget llm"


def test_can_work_quiet_hours(store_file):
    cfg = config.load_config()
    ok, reason = governor.can_work(
        cfg, counters=None, now=datetime(2026, 8, 8, 23, 30)
    )
    assert ok is False
    assert reason == "quiet hours"


def test_allowed_to_speak_muted(store_file):
    cfg = config.load_config()
    ok, reason = governor.allowed_to_speak(
        cfg, muted=True, idle_seconds=0, now=datetime(2026, 8, 8, 12, 0)
    )
    assert ok is False
    assert reason == "muted"
    ok2, reason2 = governor.allowed_to_speak(
        cfg, muted=False, idle_seconds=0, now=datetime(2026, 8, 8, 12, 0)
    )
    assert ok2 is True
    assert reason2 == "ok"


# ---------------------------------------------------------------------------
# Engagement store
# ---------------------------------------------------------------------------


def test_engagement_store_cap_500(store_file):
    for i in range(510):
        engagement_store.append_entry(
            {
                "kind": "insight",
                "title": f"topic {i}",
                "body": "x",
                "score": 0.5,
                "source": "test",
            }
        )
    data = engagement_store.load_store()
    assert len(data["entries"]) <= 500
    topics = engagement_store.recent_topics(5)
    assert topics[0] == "topic 509"


def test_engagement_mark_status(store_file):
    entry = engagement_store.append_entry(
        {"kind": "insight", "title": "hello", "body": "x", "source": "test"}
    )
    assert engagement_store.mark_status(entry["id"], "dismissed") is True
    assert engagement_store.last_engagement()["status"] == "dismissed"
    assert engagement_store.mark_status("missing", "dismissed") is False


def test_daily_counters_rollover(store_file):
    data = engagement_store.load_store()
    data["daily_counters"] = {
        "date": "2020-01-01",
        "llm": 5,
        "web": 5,
        "reads": 5,
        "speech": 5,
    }
    engagement_store.save_store(data)
    counters = engagement_store.get_daily_counters()
    assert counters["date"] == datetime.now().strftime("%Y-%m-%d")
    assert counters["llm"] == 0
    engagement_store.bump_counter("llm")
    assert engagement_store.get_daily_counters()["llm"] == 1
    engagement_store.bump_counter("bogus")
    assert engagement_store.get_daily_counters()["llm"] == 1


# ---------------------------------------------------------------------------
# Relevance + curator
# ---------------------------------------------------------------------------


def test_relevance_high_overlap():
    score = relevance.relevance_score(
        "Lumina distributed reactive runtime engine",
        sources=["Lumina is a distributed reactive runtime engine written in Rust"],
    )
    assert score >= 0.6


def test_relevance_repeat_penalty():
    sources = ["Lumina is a runtime engine"]
    plain = relevance.relevance_score(
        "Lumina runtime engine", sources=sources, history=[]
    )
    repeated = relevance.relevance_score(
        "Lumina runtime engine",
        sources=sources,
        history=["Lumina runtime engine"],
    )
    assert plain > repeated


def test_pick_best_returns_none_below_threshold(store_file):
    candidates = [
        {
            "title": "Quantum alpaca farming",
            "body": "May I ask about quantum alpaca farming?",
            "score": 0.12,
            "source": "test",
        },
        {
            "title": "Teleporting toaster",
            "body": "May I ask about teleporting toasters?",
            "score": 0.05,
            "source": "test",
        },
    ]
    assert curator.pick_best(candidates, cfg=config.load_config(), history=[]) is None


def test_pick_best_selects_high_score(store_file):
    candidates = [
        {"title": "Lumina", "body": "May I ask about Lumina?", "score": 0.9, "source": "x"},
        {"title": "Alpaca", "body": "May I ask about alpacas?", "score": 0.7, "source": "x"},
    ]
    best = curator.pick_best(candidates, cfg=config.load_config(), history=[])
    assert best is not None
    assert best["title"] == "Lumina"


def test_curator_generate_mocked(store_file, monkeypatch):
    def fake_generate(model, contents, *, system_instruction=None):
        return (
            '[{"kind":"question","title":"About Lumina",'
            '"body":"May I ask about Lumina?","source":"scanner:/x/README.md"}]'
        )

    monkeypatch.setattr(curator, "_generate_with_agent_key", fake_generate)
    sources = {
        "projects": [],
        "memory": {
            "interests": {"lumina": "Lumina is a distributed reactive language runtime"}
        },
        "brief": "",
        "notes": [],
        "sources_seen": ["memory:interests:lumina"],
    }
    candidates = curator.generate_candidates(
        sources=sources, cfg=config.load_config()
    )
    assert candidates
    assert isinstance(candidates[0]["score"], float)
    assert candidates[0]["kind"] == "question"


def test_curator_local_fallback_no_key(store_file, monkeypatch):
    def boom(model, contents, *, system_instruction=None):
        raise RuntimeError("no key")

    monkeypatch.setattr(curator, "_generate_with_agent_key", boom)
    sources = {
        "projects": [],
        "memory": {"preferences": {"tech_interests": "Running local AI models"}},
        "brief": "",
        "notes": [],
        "sources_seen": [],
    }
    candidates = curator.generate_candidates(
        sources=sources, cfg=config.load_config()
    )
    assert candidates
    assert candidates[0]["kind"] == "question"


# ---------------------------------------------------------------------------
# Scanner (blocklist safety)
# ---------------------------------------------------------------------------


def test_scanner_blocklist(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Project AGENTS\nWe build Lumina here.")
    (root / "README.md").write_text("# README\nHello")
    (root / "config").mkdir()
    (root / "config" / "api_keys.json").write_text('{"key": "sk-test"}')
    (root / "secret.txt").write_text("top secret")
    (root / "key.pem").write_text("pem")
    (root / "token.txt").write_text("tok")
    (root / ".env").write_text("ENV=1")

    monkeypatch.setattr(scanner, "registry", lambda: [str(root)])
    result = scanner.collect_sources({})
    blob = json.dumps(result)
    assert "We build Lumina here." in blob
    for blocked in ("api_keys.json", "secret.txt", "key.pem", "token.txt", ".env"):
        assert blocked not in blob
    seen = " ".join(result.get("sources_seen", []))
    assert "AGENTS.md" in seen
    for blocked in ("api_keys.json", "secret.txt", "key.pem", "token.txt", ".env"):
        assert blocked not in seen


def test_scanner_memory_fallback_empty_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "registry", lambda: [])
    result = scanner.collect_sources({})
    assert result["projects"] == []
    assert "sources_seen" in result


# ---------------------------------------------------------------------------
# Research ideas + project research
# ---------------------------------------------------------------------------


def test_research_ideas_cycle(store_file):
    memory = {
        "interests": {"rust": {"value": "Rust systems programming"}},
        "preferences": {
            "tech_interests": {"value": "Local AI models"},
            "fable_5_interest": {"value": "Fable 5 Mythos model"},
        },
    }
    added = research_ideas_store.seed_from_memory(memory)
    assert added == 3

    first = research_ideas_store.pick_next_topic()
    assert first is not None
    assert first["times_researched"] == 0

    research_ideas_store.mark_done(first["id"], result="news")
    # A researched topic is excluded from the recent window.
    second = research_ideas_store.pick_next_topic()
    assert second is not None
    assert second["id"] != first["id"]

    for idea in research_ideas_store.topics():
        research_ideas_store.mark_done(idea["id"], result="news")
    assert research_ideas_store.pick_next_topic() is None

    research_ideas_store.add_idea("Brand new topic", "memory:interests:new")
    picked = research_ideas_store.pick_next_topic()
    assert picked is not None
    assert picked["topic"] == "Brand new topic"


def test_research_trim_no_secret_leak():
    long_text = "Interesting news about the world " + "expanding detail " * 400
    out = project_research._trim_result(long_text, max_chars=100)
    assert len(out) <= 100
    assert out.endswith("…")

    secret = "The key was sk-abcdefghijklmnopqrstuvwxyz1234567890 and more text"
    out2 = project_research._trim_result(secret, max_chars=2000)
    assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in out2
    assert "redacted" in out2


def test_maybe_research_budget_respects_cap(store_file, monkeypatch):
    cfg = config.load_config()
    counters = {"date": "2026-08-08", "llm": 0, "web": 12, "reads": 0, "speech": 0}
    monkeypatch.setattr(
        project_research, "_search_topic", lambda topic: "curated news"
    )
    assert project_research.maybe_research(cfg=cfg, counters=counters) is None


# ---------------------------------------------------------------------------
# Tool (actions/proactive.py)
# ---------------------------------------------------------------------------


def test_tool_status(store_file):
    out = proactive_tool(parameters={"action": "status"})
    assert "enabled" in out
    assert "quiet window" in out
    assert "web" in out


def test_tool_on_your_mind_quiet(store_file, monkeypatch):
    def should_not_call(*args, **kwargs):
        raise AssertionError("on_your_mind must never call the LLM")

    monkeypatch.setattr(curator, "_generate_with_agent_key", should_not_call)
    out = proactive_tool(parameters={"action": "on_your_mind"})
    assert out == "engine quiet: nothing to say yet"


def test_tool_configure_and_budget(store_file):
    out = proactive_tool(
        parameters={"action": "configure", "settings": {"pacing_minutes": 45}}
    )
    assert "pacing_minutes" in out
    assert config.load_config()["pacing_minutes"] == 45
    budget_out = proactive_tool(parameters={"action": "budget"})
    assert "llm" in budget_out


# ---------------------------------------------------------------------------
# run() integration (delivery logic)
# ---------------------------------------------------------------------------

_MOCK_SOURCES = {
    "projects": [],
    "memory": {"interests": {"test": "Test project insight thought"}},
    "brief": "",
    "notes": [],
    "sources_seen": ["memory:interests:test"],
}

_MOCK_JSON = (
    '[{"kind":"question","title":"Test insight",'
    '"body":"May I share a thought about the test project insight, sir?",'
    '"source":"memory:interests:test"}]'
)


def _install_run_mocks(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "proactive_config.json")
    monkeypatch.setattr(
        engagement_store, "ENGAGEMENT_FILE", tmp_path / "proactive_engagement.json"
    )
    monkeypatch.setattr(
        research_ideas_store, "IDEAS_FILE", tmp_path / "research_ideas.json"
    )
    monkeypatch.setattr(scanner, "collect_sources", lambda cfg=None: _MOCK_SOURCES)
    monkeypatch.setattr(
        curator,
        "_generate_with_agent_key",
        lambda model, contents, *, system_instruction=None: _MOCK_JSON,
    )
    monkeypatch.setattr(project_research, "maybe_research", lambda **kwargs: None)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))


def test_run_delivers_when_ok(tmp_path, monkeypatch):
    _install_run_mocks(monkeypatch, tmp_path)
    card = asyncio.run(
        proactive.run(
            muted=False,
            session_ok=True,
            idle_seconds=0,
            tick=datetime(2026, 8, 8, 12, 0),
        )
    )
    assert card is not None
    assert card["deliver"] is True
    assert card["reason"] == "ok"
    assert engagement_store.last_engagement()["status"] == "spoken"
    counters = engagement_store.get_daily_counters()
    assert counters["llm"] == 1
    assert counters["reads"] == 1
    assert counters["speech"] == 1


def test_run_queues_when_muted(tmp_path, monkeypatch):
    _install_run_mocks(monkeypatch, tmp_path)
    card = asyncio.run(
        proactive.run(
            muted=True,
            session_ok=True,
            idle_seconds=0,
            tick=datetime(2026, 8, 8, 12, 0),
        )
    )
    assert card is not None
    assert card["deliver"] is False
    assert card["reason"] == "muted"
    assert engagement_store.last_engagement()["status"] == "queued"
    triggers = list((tmp_path / ".lucas" / "triggers").glob("trigger_proactive_*.json"))
    assert len(triggers) == 1


def test_run_quiet_hours_skips(tmp_path, monkeypatch, caplog):
    _install_run_mocks(monkeypatch, tmp_path)
    caplog.set_level(logging.INFO)
    card = asyncio.run(
        proactive.run(
            muted=False,
            session_ok=True,
            idle_seconds=0,
            tick=datetime(2026, 8, 8, 23, 30),
        )
    )
    assert card is None
    assert "PROACTIVE SKIPPED: quiet hours" in caplog.text


def test_day_in_life_budget_sim(tmp_path, monkeypatch):
    """12 ticks in one day: hard caps on llm/reads/speech hold (SPEC P1)."""
    _install_run_mocks(monkeypatch, tmp_path)
    for hour in range(0, 24, 2):
        asyncio.run(
            proactive.run(
                muted=False,
                session_ok=True,
                idle_seconds=0,
                tick=datetime(2026, 8, 1, hour, 0),
            )
        )
    counters = engagement_store.get_daily_counters()
    assert counters["llm"] <= 6
    assert counters["reads"] <= 6
    assert counters["speech"] <= 3


# ---------------------------------------------------------------------------
# Scanner semantic source (SPEC Upgrade B)
# ---------------------------------------------------------------------------


def test_collect_semantic_disabled_flag_skips_recall(monkeypatch):
    def must_not_recall(query, k=3):
        raise AssertionError("recall must not be called when disabled")

    monkeypatch.setattr(semantic_memory, "recall", must_not_recall)
    cfg = {"thresholds": {"semantic_enabled": False}}
    assert scanner._collect_semantic(cfg) == ([], [])


def test_collect_semantic_includes_tomorrow_event_query_hits(monkeypatch):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    fake_cal = {
        "events_by_date": {
            tomorrow: [{"time": "09:00", "description": "Dentist appointment"}]
        },
        "daily_routines": [],
    }
    calls: list[tuple] = []

    def fake_recall(query, k=3):
        calls.append((query, k))
        return ["[fact] User mentioned fearing dentists"]

    monkeypatch.setattr(calendar_store, "load", lambda: fake_cal)
    monkeypatch.setattr(semantic_memory, "recall", fake_recall)
    items, seen = scanner._collect_semantic({})
    assert len(items) == 1
    assert items[0]["path"].startswith("semantic:")
    assert "dentists" in items[0]["text"]
    assert seen == ["semantic:fact:0"]
    assert any("Dentist appointment" in query for query, _ in calls)
    assert all(k == 2 for _, k in calls)


def test_collect_semantic_blocklists_secret_like_memory(monkeypatch):
    fake_cal = {"events_by_date": {}, "daily_routines": []}
    monkeypatch.setattr(calendar_store, "load", lambda: fake_cal)
    monkeypatch.setattr(
        semantic_memory,
        "recall",
        lambda query, k=3: ["[fact] my api_keys backup is at home"],
    )
    assert scanner._collect_semantic({}) == ([], [])


def test_collect_semantic_truncates_to_budget(monkeypatch):
    fake_cal = {"events_by_date": {}, "daily_routines": []}
    monkeypatch.setattr(calendar_store, "load", lambda: fake_cal)

    def fake_recall(query, k=3):
        return ["[fact] " + "alpha detail " * 20, "[conversation] " + "beta detail " * 20]

    monkeypatch.setattr(semantic_memory, "recall", fake_recall)
    cfg = {"thresholds": {"semantic_k": 2, "semantic_max_chars": 128}}
    items, seen = scanner._collect_semantic(cfg)
    assert all(len(item["text"]) <= 64 for item in items)
    assert sum(len(item["text"]) for item in items) <= 128
    assert seen == ["semantic:fact:0", "semantic:conversation:1"]


def test_collect_sources_dict_contains_semantic_key(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "registry", lambda: [])
    monkeypatch.setattr(semantic_memory, "recall", lambda query, k=3: [])
    result = scanner.collect_sources({})
    assert isinstance(result.get("semantic"), list)
    fallback = scanner.collect_memory_sources()
    assert isinstance(fallback.get("semantic"), list)


def test_fmt_sources_renders_semantic_section():
    sources = {
        "semantic": [{"path": "semantic:fact", "text": "[fact] likes rust"}]
    }
    out = curator._fmt_sources(sources)
    assert "semantic:fact" in out
    assert "[fact] likes rust" in out
    assert curator._fmt_sources({"semantic": []}).strip() == ""
    assert curator._fmt_sources({}).strip() == ""


def test_configure_clamps_semantic_k_and_max_chars(monkeypatch):
    # configure()/_clamp_section live in core/proactive/__init__ (out of scope
    # for this subtask), so clamping is asserted at the scanner-side
    # consumption point instead.
    cfg = {
        "thresholds": {
            "semantic_enabled": True,
            "semantic_k": 99,
            "semantic_max_chars": 1,
        }
    }
    assert scanner._clamp_semantic_cfg(cfg) == (True, 5, 128)

    fake_cal = {"events_by_date": {}, "daily_routines": []}
    monkeypatch.setattr(calendar_store, "load", lambda: fake_cal)
    monkeypatch.setattr(
        semantic_memory,
        "recall",
        lambda query, k=3: ["[fact] " + "y" * 500],
    )
    items, _seen = scanner._collect_semantic(cfg)
    # effective k=5 and max_chars=128 -> per-hit budget 128 // 5 == 25 chars
    assert len(items) == 1
    assert len(items[0]["text"]) == 25


def test_collect_semantic_weekday_fallback_when_no_events(monkeypatch):
    fake_cal = {"events_by_date": {}, "daily_routines": []}
    captured: dict = {}

    def fake_recall(query, k=3):
        captured["query"] = query
        return ["[fact] something relevant"]

    monkeypatch.setattr(calendar_store, "load", lambda: fake_cal)
    monkeypatch.setattr(semantic_memory, "recall", fake_recall)
    items, seen = scanner._collect_semantic({})
    assert len(items) == 1
    assert seen == ["semantic:fact:0"]
    assert captured["query"].strip() != ""
    assert datetime.now().strftime("%A") in captured["query"]