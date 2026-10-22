"""Tests for core/grounding/resolver — resolve_intent, router_click,
destructive-action confirmation handshake, retries, and the layer cascade.
All hermetic: layers are mocked at module level."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.grounding import (
    SOURCE_A11Y,
    SOURCE_NONE,
    SOURCE_OCR,
    SOURCE_TEMPLATE,
    SOURCE_VISION,
    clear_pending_confirmations,
    is_destructive,
    resolve_intent,
    router_click,
)
from core.grounding import atspi_tree, capture, ocr_grounding, resolver, template_grounding, vision_crop
from core.grounding.confirms import _CONFIRM_TTL_SEC


@pytest.fixture(autouse=True)
def _clean_confirmations():
    clear_pending_confirmations()
    yield
    clear_pending_confirmations()


def _disable_all_layers(monkeypatch, *, a11y=True, ocr=True, tpl=True, vision=True):
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: a11y)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: ocr)
    monkeypatch.setattr(template_grounding, "template_available", lambda: tpl)
    monkeypatch.setattr(vision_crop, "_GENAI", vision)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "key" if vision else None)
    monkeypatch.setattr(resolver.time, "sleep", lambda s: None)


def _fake_a11y(monkeypatch, center=(100, 200), node=None):
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "find_node", lambda target, role=None, window_hint=None: node or object())
    monkeypatch.setattr(atspi_tree, "node_global_center", lambda n: center)
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))


# ---------------------------------------------------------------------------
# is_destructive
# ---------------------------------------------------------------------------


def test_is_destructive_keywords():
    for phrase in (
        "delete the file",
        "remove item",
        "clear history",
        "send message",
        "submit form",
        "pay now",
        "purchase item",
        "buy ticket",
        "close mail tab",
        "quit app",
        "shut down the pc",
        "restart system",
        "format disk",
        "wipe drive",
        "uninstall program",
    ):
        assert is_destructive(phrase), phrase


def test_is_destructive_negative():
    assert is_destructive("open settings") is False
    assert is_destructive("save document") is False
    assert is_destructive("") is False
    assert is_destructive(None) is False


# ---------------------------------------------------------------------------
# resolve_intent
# ---------------------------------------------------------------------------


def test_resolve_intent_empty_target_zero_network(monkeypatch):
    _disable_all_layers(monkeypatch)
    vision_spy = SimpleNamespace(calls=0)

    def fake_vision(*a, **k):
        vision_spy.calls += 1
        return None

    monkeypatch.setattr(vision_crop, "vision_locate", fake_vision)
    result = resolve_intent("   ")
    assert result.found is False
    assert result.source == SOURCE_NONE
    assert "no target text" in result.note
    assert vision_spy.calls == 0


def test_resolve_intent_a11y(monkeypatch):
    _disable_all_layers(monkeypatch)
    _fake_a11y(monkeypatch, center=(100, 200))
    result = resolve_intent("Save")
    assert result.found is True
    assert result.source == SOURCE_A11Y
    assert (result.x, result.y) == (100, 200)
    assert result.label == "Save"


def test_resolve_intent_a11y_clamps_coords(monkeypatch):
    _disable_all_layers(monkeypatch)
    _fake_a11y(monkeypatch, center=(5000, 5000))
    result = resolve_intent("Save")
    assert result.found is True
    assert (result.x, result.y) == (1919, 1079)


def test_resolve_intent_ocr_fallback(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, tpl=False, vision=False)
    from core.grounding.models import WordBox

    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: True)
    monkeypatch.setattr(capture, "capture_screen", lambda: ("img", 100, 100))
    monkeypatch.setattr(ocr_grounding, "ocr_words", lambda img: [WordBox("Save", 10, 20, 30, 40, conf=0.95)])
    monkeypatch.setattr(ocr_grounding, "match_words", lambda words, target: words[0])
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    result = resolve_intent("Save")
    assert result.found is True
    assert result.source == SOURCE_OCR
    assert (result.x, result.y) == (25, 40)
    assert result.confidence == 0.95


def test_resolve_intent_template_layer(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(capture, "capture_screen", lambda: ("img", 100, 100))
    monkeypatch.setattr(template_grounding, "template_available", lambda: True)
    monkeypatch.setattr(template_grounding, "template_match", lambda img, target: (0.9, 300, 400))
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    result = resolve_intent("save button")
    assert result.found is True
    assert result.source == SOURCE_TEMPLATE
    assert (result.x, result.y) == (300, 400)


def test_resolve_intent_vision_last(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, tpl=False, vision=True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "key")
    monkeypatch.setattr("memory.config_manager.get_gemini_key", lambda: "key")
    monkeypatch.setattr(vision_crop, "vision_locate", lambda *a, **k: (700, 800))
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    result = resolve_intent("save")
    assert result.found is True
    assert result.source == SOURCE_VISION
    assert (result.x, result.y) == (700, 800)


def test_resolve_intent_all_miss_no_exception(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, tpl=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)

    result = resolve_intent("Ghost Element")
    assert result.found is False
    assert result.source == SOURCE_NONE
    assert "a11y unavailable" in result.note
    assert "ocr unavailable" in result.note


def test_resolve_intent_layer_exception_degrades(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=True, ocr=False, tpl=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    monkeypatch.setattr(atspi_tree, "find_node", lambda target, role=None, window_hint=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)

    result = resolve_intent("Save")
    assert result.found is False  # layer exception swallowed; falls through


def test_resolve_intent_uses_window_hint_for_vision(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, tpl=False, vision=True)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", True)
    monkeypatch.setattr(vision_crop, "get_gemini_key", lambda: "key")
    monkeypatch.setattr("memory.config_manager.get_gemini_key", lambda: "key")
    seen = {}

    def fake_vision(target, *, window_rect=None, cursor_center=None, max_calls=3):
        seen["window_rect"] = window_rect
        return (1, 2)

    monkeypatch.setattr(vision_crop, "vision_locate", fake_vision)
    monkeypatch.setattr(resolver, "window_rect_for_hint", lambda hint: (0, 0, 800, 600))
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    result = resolve_intent("save", window_hint="chrome")
    assert result.found is True
    assert seen["window_rect"] == (0, 0, 800, 600)


# ---------------------------------------------------------------------------
# router_click — return strings
# ---------------------------------------------------------------------------


def test_router_click_success_string_and_click(monkeypatch):
    _fake_a11y(monkeypatch, center=(100, 200))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: "")

    clicks = []

    def click_fn(x, y):
        clicks.append((x, y))

    result = router_click("Save", click_fn=click_fn)
    assert result == "Clicked 'Save' at (100,200) via a11y"
    assert clicks == [(100, 200)]


def test_router_click_not_found_string(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, tpl=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    result = router_click("Ghost", click_fn=lambda x, y: None)
    assert result == "Element not found on screen: 'Ghost'"


def test_router_click_empty_target(monkeypatch):
    _disable_all_layers(monkeypatch)
    result = router_click("", click_fn=lambda x, y: None)
    assert result == "Element not found on screen: ''"


def test_router_click_advisory_appended(monkeypatch):
    _fake_a11y(monkeypatch, center=(100, 200))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(
        resolver, "verify_after_click",
        lambda result, delay_s=0.8: "element still present at (100, 200)",
    )
    result = router_click("Save", click_fn=lambda x, y: None)
    assert result.startswith("Clicked 'Save' at (100,200) via a11y")
    assert "click injected but post-verify could not confirm 'Save'" in result
    assert "(verify: element still present at (100, 200))" in result


def test_router_click_verify_disabled(monkeypatch):
    _fake_a11y(monkeypatch, center=(1, 2))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    spy = SimpleNamespace(calls=0)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: spy.__setattr__("calls", spy.calls + 1) or "x")
    result = router_click("Save", click_fn=lambda x, y: None, verify=False)
    assert result == "Clicked 'Save' at (1,2) via a11y"
    assert spy.calls == 0


def test_router_click_no_verify_for_template_source(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=False, ocr=False, tpl=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: False)
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: True)
    monkeypatch.setattr(template_grounding, "template_match", lambda img, target: (0.8, 5, 6))
    monkeypatch.setattr(capture, "capture_screen", lambda: ("img", 100, 100))
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))
    spy = SimpleNamespace(calls=0)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: spy.__setattr__("calls", spy.calls + 1) or "x")
    result = router_click("save button", click_fn=lambda x, y: None)
    assert result == "Clicked 'save button' at (5,6) via template"
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# destructive confirmation handshake
# ---------------------------------------------------------------------------


def test_destructive_first_call_confirms_no_click(monkeypatch):
    _fake_a11y(monkeypatch, center=(10, 20))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    clicks = []
    result = router_click("delete the file", click_fn=lambda x, y: clicks.append((x, y)))
    assert result.startswith("CONFIRM_REQUIRED: 'delete the file'")
    assert "ask the user to confirm" in result
    assert clicks == []


def test_destructive_second_call_within_ttl_clicks(monkeypatch):
    _fake_a11y(monkeypatch, center=(10, 20))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: "")
    clicks = []

    first = router_click("delete the file", click_fn=lambda x, y: clicks.append((x, y)))
    assert first.startswith("CONFIRM_REQUIRED")
    assert clicks == []

    second = router_click("delete the file", click_fn=lambda x, y: clicks.append((x, y)))
    assert second.startswith("Clicked")
    assert clicks == [(10, 20)]


def test_destructive_after_ttl_confirms_again(monkeypatch):
    _fake_a11y(monkeypatch, center=(10, 20))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver.time, "sleep", lambda s: None)
    from core.grounding import confirms

    fake_time = {"t": 1000.0}
    monkeypatch.setattr(confirms.time, "monotonic", lambda: fake_time["t"])
    clicks = []

    first = router_click("pay now", click_fn=lambda x, y: clicks.append((x, y)))
    assert first.startswith("CONFIRM_REQUIRED")

    # TTL expires (time jumps beyond the 60s window)
    fake_time["t"] += _CONFIRM_TTL_SEC + 1
    second = router_click("pay now", click_fn=lambda x, y: clicks.append((x, y)))
    assert second.startswith("CONFIRM_REQUIRED")
    assert clicks == []


def test_destructive_different_targets_independent(monkeypatch):
    _fake_a11y(monkeypatch, center=(1, 1))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: "")
    clicks = []

    r1 = router_click("clear history", click_fn=lambda x, y: clicks.append((x, y)))
    assert r1.startswith("CONFIRM_REQUIRED")
    r2 = router_click("submit form", click_fn=lambda x, y: clicks.append((x, y)))
    assert r2.startswith("CONFIRM_REQUIRED")
    # first target still confirmed this round
    r3 = router_click("clear history", click_fn=lambda x, y: clicks.append((x, y)))
    assert r3.startswith("Clicked")
    assert len(clicks) == 1


def test_clear_pending_confirmations_resets(monkeypatch):
    _fake_a11y(monkeypatch, center=(1, 1))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: "")
    clicks = []

    assert router_click("quit app", click_fn=lambda x, y: clicks.append((x, y))).startswith("CONFIRM_REQUIRED")
    clear_pending_confirmations()
    assert router_click("quit app", click_fn=lambda x, y: clicks.append((x, y))).startswith("CONFIRM_REQUIRED")
    assert clicks == []


def test_router_click_injection_failure_surfaced(monkeypatch):
    """R3: when click injection fails, the error is surfaced, not swallowed."""
    _fake_a11y(monkeypatch, center=(1, 2))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(
        resolver, "_default_click", lambda x, y: (_ for _ in ()).throw(RuntimeError("injector down"))
    )
    result = router_click("Save")
    assert result == "click failed: injector down"


def test_router_click_custom_click_fn_used(monkeypatch):
    """click_fn passed by callers (e.g. computer_control._click) is invoked."""
    _fake_a11y(monkeypatch, center=(5, 7))
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: False)
    monkeypatch.setattr(template_grounding, "template_available", lambda: False)
    monkeypatch.setattr(vision_crop, "_GENAI", False)
    monkeypatch.setattr(resolver, "verify_after_click", lambda result, delay_s=0.8: "")
    clicks = []
    result = router_click("Save", click_fn=lambda x, y: clicks.append((x, y)))
    assert result == "Clicked 'Save' at (5,7) via a11y"
    assert clicks == [(5, 7)]


# ---------------------------------------------------------------------------
# retry behavior
# ---------------------------------------------------------------------------


def test_resolve_intent_retries_a11y_then_falls_to_ocr(monkeypatch):
    _disable_all_layers(monkeypatch, a11y=True, ocr=True, tpl=False, vision=False)
    monkeypatch.setattr(atspi_tree, "a11y_available", lambda: True)
    attempts = {"n": 0}
    monkeypatch.setattr(
        atspi_tree, "find_node",
        lambda target, role=None, window_hint=None: (attempts.__setitem__("n", attempts["n"] + 1) or None),
    )
    monkeypatch.setattr(ocr_grounding, "ocr_available", lambda: True)
    from core.grounding.models import WordBox

    monkeypatch.setattr(capture, "capture_screen", lambda: ("img", 100, 100))
    monkeypatch.setattr(ocr_grounding, "ocr_words", lambda img: [WordBox("Save", 0, 0, 10, 10)])
    monkeypatch.setattr(ocr_grounding, "match_words", lambda words, target: words[0])
    monkeypatch.setattr(capture, "screen_size", lambda: (1920, 1080))

    result = resolve_intent("Save")
    assert result.found is True
    assert result.source == SOURCE_OCR
    assert attempts["n"] >= 1