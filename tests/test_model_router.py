"""Tests for memory.model_router — gemini→groq circuit-breaker coding router."""

from __future__ import annotations

import json
import logging

import pytest

import agent.error_handler as error_handler
import agent.executor as executor
import actions.coding_workspace as coding_workspace
import agent.planner as planner
import memory.gemini_text as gemini_text
import memory.groq_text as groq_text
import memory.model_router as model_router
from memory.coding_model import get_search_model


def _patch_legs(monkeypatch, gemini_fn, groq_fn) -> None:
    """Point both provider modules at test stubs (no network ever)."""
    monkeypatch.setattr(gemini_text, "generate_text", gemini_fn)
    monkeypatch.setattr(groq_text, "generate_text_groq", groq_fn)


# --- unit tests ----------------------------------------------------------


def test_generate_routed_primary_success_returns_gemini_and_logs_provider(
    monkeypatch, caplog
):
    model_router.reset_health()

    def gemini_ok(model, contents, *, system_instruction=None):
        return "gemini answer"

    def groq_never(model, contents, *, system_instruction=None):
        raise AssertionError("groq must not be called while gemini is healthy")

    _patch_legs(monkeypatch, gemini_ok, groq_never)

    with caplog.at_level(logging.INFO):
        result = model_router.generate_routed(
            "gemini-3.1-flash-lite", "hello", system_instruction="sys"
        )

    assert result == "gemini answer"
    assert model_router.last_provider() == "gemini"
    assert "served by gemini" in caplog.text


def test_generate_routed_falls_back_after_gemini_exception(monkeypatch, caplog):
    model_router.reset_health()

    def gemini_down(model, contents, *, system_instruction=None):
        raise RuntimeError("Gemini outage for this call")

    def groq_ok(model, contents, *, system_instruction=None):
        assert model == model_router.GROQ_FALLBACK_MODEL
        assert contents == "hello"
        return "groq answer"

    _patch_legs(monkeypatch, gemini_down, groq_ok)

    with caplog.at_level(logging.WARNING):
        result = model_router.generate_routed("any-model", "hello")

    assert result == "groq answer"
    assert model_router.last_provider() == "groq"
    assert "falling back" in caplog.text


def test_generate_routed_breaker_opens_after_threshold_and_skips_primary(monkeypatch):
    model_router.reset_health()
    calls = {"gemini": 0, "groq": 0}

    def gemini_down(model, contents, *, system_instruction=None):
        calls["gemini"] += 1
        raise RuntimeError("Gemini hard down")

    def groq_ok(model, contents, *, system_instruction=None):
        calls["groq"] += 1
        return "groq answer"

    _patch_legs(monkeypatch, gemini_down, groq_ok)

    results = [model_router.generate_routed("m", f"c{i}") for i in range(4)]

    # Three failures arm the breaker; the 4th call never touches the primary.
    assert calls["gemini"] == 3
    assert calls["groq"] == 4
    assert results == ["groq answer"] * 4


def test_generate_routed_breaker_closes_after_cooldown_probe_success(monkeypatch):
    model_router.reset_health()
    clock = {"now": 1000.0}
    monkeypatch.setattr(model_router.time, "time", lambda: clock["now"])
    calls = {"gemini": 0}

    def gemini_flaky(model, contents, *, system_instruction=None):
        calls["gemini"] += 1
        if clock["now"] < 1000.0 + float(model_router._COOLDOWN_SEC):
            raise RuntimeError("Gemini outage window")
        return "gemini recovered"

    def groq_ok(model, contents, *, system_instruction=None):
        return "groq answer"

    _patch_legs(monkeypatch, gemini_flaky, groq_ok)

    for _ in range(3):
        assert model_router.generate_routed("m", "c") == "groq answer"
    assert calls["gemini"] == 3

    clock["now"] += float(model_router._COOLDOWN_SEC) + 1.0

    assert model_router.generate_routed("m", "c") == "gemini recovered"
    assert model_router.last_provider() == "gemini"
    assert model_router._health["gemini"]["fails"] == 0
    assert model_router._health["gemini"]["open_until"] == 0.0


def test_generate_routed_both_fail_raises_runtime_error_naming_both(monkeypatch):
    model_router.reset_health()

    def gemini_down(model, contents, *, system_instruction=None):
        raise ValueError("Gemini returned an empty response.")

    def groq_down(model, contents, *, system_instruction=None):
        raise RuntimeError("Groq HTTP 503: upstream unavailable")

    _patch_legs(monkeypatch, gemini_down, groq_down)

    with pytest.raises(RuntimeError) as excinfo:
        model_router.generate_routed("m", "c")

    message = str(excinfo.value)
    assert "Gemini returned an empty response." in message
    assert "Groq HTTP 503: upstream unavailable" in message


def test_generate_routed_missing_groq_key_surfaces_primary_error(monkeypatch):
    model_router.reset_health()
    calls = {"gemini": 0, "groq": 0}

    def gemini_down(model, contents, *, system_instruction=None):
        calls["gemini"] += 1
        raise RuntimeError("Gemini quota exceeded")

    def groq_no_key(model, contents, *, system_instruction=None):
        calls["groq"] += 1
        raise RuntimeError(
            'No Groq API key. Add keys to config/agent_keys.json under "groq".'
        )

    _patch_legs(monkeypatch, gemini_down, groq_no_key)

    first_error = ""
    for _ in range(3):
        with pytest.raises(RuntimeError) as excinfo:
            model_router.generate_routed("m", "c")
        if not first_error:
            first_error = str(excinfo.value)
        # Keep the primary leg healthy so only Groq trips its breaker.
        model_router.reset_health("gemini")

    assert "Gemini quota exceeded" in first_error
    assert "No Groq API key" in first_error

    with pytest.raises(RuntimeError) as excinfo:
        model_router.generate_routed("m", "c")

    # Groq breaker is open: surfaced immediately, no second Groq attempt.
    assert "Gemini quota exceeded" in str(excinfo.value)
    assert calls["gemini"] == 4
    assert calls["groq"] == 3


def test_last_provider_reflects_serving_leg(monkeypatch):
    model_router.reset_health()
    assert model_router.last_provider() == ""

    def gemini_down(model, contents, *, system_instruction=None):
        raise RuntimeError("down once")

    _patch_legs(
        monkeypatch,
        lambda m, c, **kw: "gemini answer",
        gemini_down,
    )
    assert model_router.generate_routed("m", "c") == "gemini answer"
    assert model_router.last_provider() == "gemini"

    _patch_legs(monkeypatch, gemini_down, lambda m, c, **kw: "groq answer")
    assert model_router.generate_routed("m", "c") == "groq answer"
    assert model_router.last_provider() == "groq"


def test_reset_health_clears_state(monkeypatch):
    model_router.reset_health()
    calls = {"gemini": 0}

    def gemini_down(model, contents, *, system_instruction=None):
        calls["gemini"] += 1
        raise RuntimeError("outage")

    _patch_legs(monkeypatch, gemini_down, lambda m, c, **kw: "groq answer")
    for _ in range(3):
        model_router.generate_routed("m", "c")
    assert calls["gemini"] == 3  # breaker now open on gemini

    model_router.reset_health()

    def gemini_ok(model, contents, *, system_instruction=None):
        return "gemini answer"

    def groq_never(model, contents, *, system_instruction=None):
        raise AssertionError("groq must not be called after reset")

    _patch_legs(monkeypatch, gemini_ok, groq_never)
    assert model_router.generate_routed("m", "c") == "gemini answer"
    assert model_router.last_provider() == "gemini"


# --- integration: one per migrated consumer -------------------------------


def test_create_plan_dispatches_via_generate_routed_with_search_model(monkeypatch):
    model_router.reset_health()
    captured = {}

    def routed_stub(model, contents, *, system_instruction=None):
        captured["model"] = model
        return json.dumps(
            {
                "goal": "goal",
                "steps": [
                    {
                        "step": 1,
                        "tool": "web_search",
                        "description": "search it",
                        "parameters": {"query": "q"},
                        "critical": True,
                    }
                ],
            }
        )

    monkeypatch.setattr(model_router, "generate_routed", routed_stub)

    plan = planner.create_plan("goal")

    assert captured["model"] == get_search_model()
    assert plan["steps"][0]["tool"] == "web_search"


def test_analyze_error_dispatches_via_generate_routed_with_search_model(monkeypatch):
    model_router.reset_health()
    captured = {}

    def routed_stub(model, contents, *, system_instruction=None):
        captured["model"] = model
        return json.dumps(
            {
                "decision": "retry",
                "reason": "transient failure",
                "max_retries": 1,
                "user_message": "Retrying",
            }
        )

    monkeypatch.setattr(model_router, "generate_routed", routed_stub)

    step = {"step": 1, "tool": "web_search", "description": "Search"}
    result = error_handler.analyze_error(step, "boom", attempt=1)

    assert captured["model"] == get_search_model()
    assert result["decision"] == error_handler.ErrorDecision.RETRY


def test_detect_language_dispatches_via_generate_routed_with_search_model(monkeypatch):
    model_router.reset_health()
    captured = {}

    def routed_stub(model, contents, *, system_instruction=None):
        captured["model"] = model
        return "English"

    # executor imports generate_routed at module level; patch that binding.
    monkeypatch.setattr(executor, "generate_routed", routed_stub)

    assert executor._detect_language("hello world") == "English"
    assert captured["model"] == get_search_model()


def test_gemini_generate_dispatches_via_generate_routed_with_coding_model(monkeypatch):
    model_router.reset_health()
    captured = {}

    def routed_stub(model, contents, *, system_instruction=None):
        captured["model"] = model
        captured["system_instruction"] = system_instruction
        return "ok"

    # coding_workspace imports generate_routed at module level; patch that binding.
    monkeypatch.setattr(coding_workspace, "generate_routed", routed_stub)
    monkeypatch.setattr(coding_workspace, "get_coding_model", lambda: "test-model")

    result = coding_workspace._gemini_generate("prompt")

    assert result == "ok"
    assert captured["model"] == "test-model"
    assert captured["system_instruction"] is not None
