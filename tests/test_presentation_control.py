"""Tests for Lucas Presentation Engine — slide generation + action module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from actions import presentation_control as pc_mod
from actions.presentation_control import (
    TOOL_SCHEMA,
    _derive_window_key,
    _parse_labels_values,
    _slugify_key,
    presentation_control,
)
from core import presentation_core as pc


@pytest.fixture(autouse=True)
def _reset_presentation_registry():
    """Reset the module-level open-key registry before every test.

    The action module keeps `_open_presentation_keys` / `_last_presentation_key`
    in module state across calls; without a reset, nav tests would inherit the
    last key opened by an earlier test.
    """
    pc_mod._open_presentation_keys.clear()
    pc_mod._last_presentation_key = "presentation"
    yield
    pc_mod._open_presentation_keys.clear()
    pc_mod._last_presentation_key = "presentation"


# ═══════════════════════════════════════════════════════════════════
# TOOL_SCHEMA structure
# ═══════════════════════════════════════════════════════════════════


class TestToolSchema:
    def test_schema_name(self):
        assert TOOL_SCHEMA["name"] == "presentation_control"

    def test_schema_has_description(self):
        assert len(TOOL_SCHEMA["description"]) > 20

    def test_schema_has_parameters_object(self):
        assert TOOL_SCHEMA["parameters"]["type"] == "OBJECT"

    def test_schema_action_required(self):
        assert "action" in TOOL_SCHEMA["parameters"]["required"]

    def test_schema_action_in_properties(self):
        assert "action" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_title_param(self):
        assert "title" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_presentation_title_param(self):
        assert "presentation_title" in TOOL_SCHEMA["parameters"]["properties"]


# ═══════════════════════════════════════════════════════════════════
# Helper — _parse_labels_values
# ═══════════════════════════════════════════════════════════════════


class TestParseLabelsValues:
    def test_empty_string(self):
        assert _parse_labels_values("") == []

    def test_single_pair(self):
        assert _parse_labels_values("Tasks:42") == [("Tasks", "42")]

    def test_multiple_pairs(self):
        result = _parse_labels_values("Done:8;Pending:3;Total:12")
        assert result == [("Done", "8"), ("Pending", "3"), ("Total", "12")]

    def test_value_without_label(self):
        assert _parse_labels_values("hello") == [("hello", "")]

    def test_mixed_format(self):
        result = _parse_labels_values("A:1;raw;B:2")
        assert result == [("A", "1"), ("raw", ""), ("B", "2")]

    def test_whitespace_trimming(self):
        result = _parse_labels_values("  Tasks : 42 ; Done : 8 ")
        assert result == [("Tasks", "42"), ("Done", "8")]


# ═══════════════════════════════════════════════════════════════════
# Slide generation
# ═══════════════════════════════════════════════════════════════════


class TestSlideGeneration:
    def test_title_slide_has_title(self):
        result = pc.title_slide("Hello World")
        assert "Hello World" in result
        assert "title-slide" in result

    def test_title_slide_with_subtitle(self):
        result = pc.title_slide("Hello", "Subtitle text")
        assert "Hello" in result
        assert "Subtitle text" in result

    def test_title_slide_without_subtitle(self):
        result = pc.title_slide("Alone")
        assert "Alone" in result
        assert "</p>" not in result

    def test_list_slide_creates_items(self):
        result = pc.list_slide("Things", ["A", "B", "C"])
        assert "Things" in result
        assert "<li>A</li>" in result
        assert "<li>B</li>" in result
        assert "<li>C</li>" in result

    def test_list_slide_empty(self):
        result = pc.list_slide("Empty", [])
        assert "Empty" in result
        assert "<li>" not in result

    def test_stats_slide_creates_cards(self):
        result = pc.stats_slide("Stats", [("42", "Tasks"), ("8", "Done")])
        assert "Stats" in result
        assert 'class="stat-value"' in result
        assert "42" in result
        assert "Tasks" in result
        assert "Done" in result

    def test_stats_slide_empty(self):
        result = pc.stats_slide("Empty", [])
        assert "Empty" in result
        assert "stat-card" not in result

    def test_table_slide_creates_table(self):
        result = pc.table_slide(
            "Data",
            ["Name", "Value"],
            [["Alice", "10"], ["Bob", "20"]],
        )
        assert "Data" in result
        assert "<th>Name</th>" in result
        assert "<th>Value</th>" in result
        assert "<td>Alice</td>" in result
        assert "<td>Bob</td>" in result

    def test_table_slide_with_empty_rows(self):
        result = pc.table_slide("Empty", ["H1", "H2"], [])
        assert "Empty" in result
        assert "<th>H1</th>" in result
        assert "<tbody>" in result
        assert "</tbody>" in result

    def test_progress_slide_creates_bars(self):
        result = pc.progress_slide("Progress", [("Coding", 70), ("Design", 30)])
        assert "Progress" in result
        assert "Coding" in result
        assert "Design" in result
        assert 'style="width:70%"' in result
        assert 'style="width:30%"' in result

    def test_progress_slide_empty(self):
        result = pc.progress_slide("Empty", [])
        assert "Empty" in result
        assert "progress-bar" not in result

    def test_code_slide_creates_block(self):
        result = pc.code_slide("Code Snippet", "print('hello')")
        assert "Code Snippet" in result
        assert "print('hello')" in result
        assert "<pre>" in result

    def test_code_slide_empty_code(self):
        result = pc.code_slide("Empty", "")
        assert "Empty" in result
        assert "<pre><code></code></pre>" in result

    def test_text_slide_creates_paragraph(self):
        result = pc.text_slide("Note", "Some interesting text.")
        assert "Note" in result
        assert "Some interesting text." in result
        assert "<p>" in result

    def test_text_slide_empty(self):
        result = pc.text_slide("Empty", "")
        assert "Empty" in result
        assert "<p></p>" in result

    def test_all_slides_wrapped_in_slide_div(self):
        for fn in [
            pc.title_slide("T"),
            pc.list_slide("T", ["a"]),
            pc.stats_slide("T", [("1", "a")]),
            pc.table_slide("T", ["H"], [["R"]]),
            pc.progress_slide("T", [("a", 50)]),
            pc.code_slide("T", "code"),
            pc.text_slide("T", "body"),
        ]:
            assert '<div class="slide">' in fn, f"Missing slide div in {fn[:50]}"


# ═══════════════════════════════════════════════════════════════════
# build_presentation
# ═══════════════════════════════════════════════════════════════════


class TestBuildPresentation:
    def test_build_with_slides(self):
        slides = [pc.title_slide("Hello"), pc.list_slide("Items", ["a", "b"])]
        result = pc.build_presentation("Test", slides)
        assert result["title"] == "Test"
        assert len(result["slide_bodies"]) == 2
        assert "Hello" in result["slide_bodies"][0]
        assert "Items" in result["slide_bodies"][1]
        assert len(result["slide_css"]) > 100
        assert result["slide_index"] == 0
        assert result["slide_count"] == 2

    def test_build_with_labels(self):
        slides = [pc.title_slide("Hello"), pc.text_slide("Bye", "done")]
        result = pc.build_presentation("Test", slides, labels=["Intro", "End"])
        assert result["slide_labels"] == ["Intro", "End"]

    def test_build_default_labels(self):
        slides = [
            pc.title_slide("S1"),
            pc.text_slide("S2", "x"),
            pc.text_slide("S3", "y"),
        ]
        result = pc.build_presentation("Test", slides)
        assert result["slide_labels"] == ["1", "2", "3"]

    def test_build_empty_slides(self):
        result = pc.build_presentation("Empty", [])
        assert result["slide_count"] == 0
        assert result["slide_bodies"] == []
        assert result["slide_labels"] == []


# ═══════════════════════════════════════════════════════════════════
# Error handling — missing / bad params
# ═══════════════════════════════════════════════════════════════════


class TestErrorHandling:
    def test_no_action_returns_error(self):
        result = presentation_control({})
        assert "No action specified" in result

    def test_unknown_action_returns_error(self):
        result = presentation_control({"action": "nonexistent"})
        assert "Unknown action" in result

    def test_close_without_player(self):
        result = presentation_control({"action": "close_presentation"})
        assert "Cannot close presentation" in result

    def test_next_without_player(self):
        result = presentation_control({"action": "next_slide"})
        assert "Cannot advance" in result

    def test_prev_without_player(self):
        result = presentation_control({"action": "prev_slide"})
        assert "Cannot go back" in result


# ═══════════════════════════════════════════════════════════════════
# Action dispatch — happy paths with mocked player
# ═══════════════════════════════════════════════════════════════════


class TestActionDispatch:
    def test_show_title_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_title", "title": "My Title", "subtitle": "Sub"},
            player=player,
        )
        assert "My Title" in result
        player.open_presentation_slides.assert_called_once()
        args = player.open_presentation_slides.call_args[0][0]
        assert args["title"] == "My Title"
        assert "My Title" in args["slide_bodies"][0]
        assert "Sub" in args["slide_bodies"][0]

    def test_show_list_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_list", "title": "Todo", "items": "A, B, C"},
            player=player,
        )
        assert "Todo" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert "<li>A</li>" in body
        assert "<li>B</li>" in body
        assert "<li>C</li>" in body

    def test_show_stats_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {
                "action": "show_stats",
                "title": "Dashboard",
                "labels_values": "Tasks:42;Done:8",
            },
            player=player,
        )
        assert "Dashboard" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert "42" in body
        assert "Tasks" in body
        assert "8" in body
        assert "Done" in body

    def test_show_table_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {
                "action": "show_table",
                "title": "Data",
                "headers": "Name,Score",
                "rows": "Alice,90;Bob,85",
            },
            player=player,
        )
        assert "Data" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert "Alice" in body
        assert "90" in body
        assert "Bob" in body
        assert "85" in body

    def test_show_progress_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {
                "action": "show_progress",
                "title": "Progress",
                "labels_values": "Coding:70;Design:30",
            },
            player=player,
        )
        assert "Progress" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert 'style="width:70%"' in body
        assert "Coding" in body
        assert "Design" in body

    def test_show_code_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_code", "title": "Snippet", "code": "def foo(): pass"},
            player=player,
        )
        assert "Snippet" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert "def foo(): pass" in body

    def test_show_text_with_player(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_text", "title": "Note", "body": "Hello world"},
            player=player,
        )
        assert "Note" in result
        player.open_presentation_slides.assert_called_once()
        body = player.open_presentation_slides.call_args[0][0]["slide_bodies"][0]
        assert "Hello world" in body

    def test_next_slide_with_player(self):
        player = MagicMock()
        player.advance_presentation_slide.return_value = "1"
        result = presentation_control({"action": "next_slide"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(1, window="presentation")
        assert "1" in result

    def test_prev_slide_with_player(self):
        player = MagicMock()
        player.advance_presentation_slide.return_value = "-1"
        presentation_control({"action": "prev_slide"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(-1, window="presentation")

    def test_advance_alias(self):
        player = MagicMock()
        presentation_control({"action": "advance"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(1, window="presentation")

    def test_back_alias(self):
        player = MagicMock()
        presentation_control({"action": "back"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(-1, window="presentation")

    def test_close_presentation_with_player(self):
        player = MagicMock()
        result = presentation_control({"action": "close_presentation"}, player=player)
        player.close_presentation.assert_called_once_with(window="presentation")
        assert "closed" in result

    def test_presentation_title_override(self):
        player = MagicMock()
        result = presentation_control(
            {
                "action": "show_title",
                "title": "My Slide",
                "presentation_title": "Custom Pres",
            },
            player=player,
        )
        assert "My Slide" in result
        args = player.open_presentation_slides.call_args[0][0]
        assert args["title"] == "Custom Pres"

    def test_show_stats_with_malformed_labels_values(self):
        player = MagicMock()
        result = presentation_control(
            {
                "action": "show_stats",
                "title": "Stats",
                "labels_values": "no_colon_here",
            },
            player=player,
        )
        assert "Stats" in result
        player.open_presentation_slides.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_action_with_spaces(self):
        player = MagicMock()
        player.advance_presentation_slide.return_value = "1"
        result = presentation_control({"action": "  next slide  "}, player=player)
        player.advance_presentation_slide.assert_called_once_with(1, window="presentation")
        assert "1" in result

    def test_empty_list_items(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_list", "title": "Nothing", "items": ""},
            player=player,
        )
        assert "Nothing" in result
        player.open_presentation_slides.assert_called_once()

    def test_stat_with_unicode(self):
        result = pc.stats_slide("Stats", [("\u2603", "Snowmen")])
        assert "\u2603" in result
        assert "Snowmen" in result


# ═══════════════════════════════════════════════════════════════════
# Window keys — slugify, derived keys, dedupe, workspace param
# ═══════════════════════════════════════════════════════════════════


class TestWindowKeys:
    def test_slugify_basic(self):
        assert _slugify_key("Project Dashboard") == "project-dashboard"

    def test_slugify_collapses_separators(self):
        assert _slugify_key("A -- B / C") == "a-b-c"

    def test_slugify_security_path(self):
        assert _slugify_key("/etc/passwd") == "etc-passwd"

    def test_slugify_empty(self):
        assert _slugify_key("") == ""

    def test_slugify_truncates(self):
        long_title = "x" * 60
        assert len(_slugify_key(long_title)) <= 40

    def test_derive_default_presentation(self):
        assert _derive_window_key({}) == "presentation"

    def test_derive_from_title(self):
        assert _derive_window_key({"title": "Project Dashboard"}) == (
            "presentation:project-dashboard"
        )

    def test_derive_from_presentation_title(self):
        assert _derive_window_key({"presentation_title": "My Briefing"}) == (
            "presentation:my-briefing"
        )

    def test_derive_prefers_presentation_title(self):
        assert _derive_window_key({"title": "Slide", "presentation_title": "Deck"}) == (
            "presentation:deck"
        )

    def test_derive_explicit_key(self):
        assert _derive_window_key({"window_key": "custom win"}) == (
            "presentation:custom-win"
        )

    def test_show_title_derived_window_key(self):
        player = MagicMock()
        presentation_control(
            {
                "action": "show_title",
                "title": "T",
                "presentation_title": "Project Dashboard",
            },
            player=player,
        )
        assert player.open_presentation_slides.call_args[1]["window"] == (
            "presentation:project-dashboard"
        )

    def test_no_title_uses_default_presentation(self):
        player = MagicMock()
        presentation_control({"action": "show_title"}, player=player)
        assert player.open_presentation_slides.call_args[1]["window"] == "presentation"

    def test_derived_key_dedupes_with_suffix(self):
        player = MagicMock()
        presentation_control({"action": "show_title", "title": "Foo"}, player=player)
        assert player.open_presentation_slides.call_args[1]["window"] == "presentation:foo"
        presentation_control({"action": "show_title", "title": "Foo"}, player=player)
        assert player.open_presentation_slides.call_args[1]["window"] == "presentation:foo-2"

    def test_explicit_key_reopen_replaces(self):
        player = MagicMock()
        presentation_control(
            {"action": "show_title", "title": "A", "window_key": "x"}, player=player
        )
        assert player.open_presentation_slides.call_args[1]["window"] == "presentation:x"
        presentation_control(
            {"action": "show_title", "title": "B", "window_key": "x"}, player=player
        )
        assert player.open_presentation_slides.call_args[1]["window"] == "presentation:x"

    def test_nav_targets_last_opened(self):
        player = MagicMock()
        presentation_control({"action": "show_title", "title": "Foo"}, player=player)
        player.advance_presentation_slide.return_value = "1"
        presentation_control({"action": "next_slide"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(
            1, window="presentation:foo"
        )

    def test_nav_targets_explicit_window_key(self):
        player = MagicMock()
        presentation_control({"action": "show_title", "title": "Foo"}, player=player)
        player.advance_presentation_slide.return_value = "1"
        presentation_control({"action": "next_slide", "window_key": "bar"}, player=player)
        player.advance_presentation_slide.assert_called_once_with(
            1, window="presentation:bar"
        )

    def test_close_removes_key_from_registry(self):
        player = MagicMock()
        presentation_control({"action": "show_title", "title": "Foo"}, player=player)
        presentation_control({"action": "close_presentation"}, player=player)
        assert "presentation:foo" not in pc_mod._open_presentation_keys
        player.close_presentation.assert_called_once_with(window="presentation:foo")

    def test_workspace_param_switches_before_open(self, monkeypatch):
        from core import sway_control as core_sway

        player = MagicMock()
        events: list[str] = []

        def fake_switch(n):
            events.append(f"switch:{n}")
            return "Switched to workspace 7."

        monkeypatch.setattr(core_sway, "switch_workspace", fake_switch)
        player.open_presentation_slides = MagicMock(
            side_effect=lambda *a, **k: events.append("open")
        )
        presentation_control(
            {
                "action": "show_stats",
                "title": "Stats",
                "labels_values": "A:1",
                "workspace": 7,
            },
            player=player,
        )
        assert events == ["switch:7", "open"]

    def test_workspace_invalid_safe_fail_still_opens(self):
        player = MagicMock()
        result = presentation_control(
            {"action": "show_title", "title": "X", "workspace": 0},
            player=player,
        )
        player.open_presentation_slides.assert_called_once()
        assert "Invalid workspace" in result

    def test_workspace_missing_swaymsg_safe_fail_still_opens(self, monkeypatch):
        from core import sway_control as core_sway

        monkeypatch.setattr(core_sway, "switch_workspace", lambda n: "swaymsg not found.")
        player = MagicMock()
        result = presentation_control(
            {"action": "show_title", "title": "X", "workspace": 3},
            player=player,
        )
        player.open_presentation_slides.assert_called_once()
        assert "swaymsg not found" in result
