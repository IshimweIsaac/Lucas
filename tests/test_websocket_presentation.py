"""Tests for WebSocketPlayer presentation methods with the `window=` kwarg."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.websocket_server import WebSocketPlayer


def _make_player():
    server = MagicMock()
    server._player = None
    player = WebSocketPlayer(server)
    return player, server


def _last_sent(server) -> dict:
    return server.send.call_args[0][0]


_SLIDES = {
    "title": "T",
    "slide_css": "",
    "slide_bodies": ["<p>hi</p>"],
    "slide_labels": [],
    "slide_index": 0,
    "slide_count": 1,
}


def test_open_presentation_slides_uses_window_kwarg():
    player, server = _make_player()
    player.open_presentation_slides(_SLIDES, window="presentation:project-dashboard")
    sent = _last_sent(server)
    assert sent["type"] == "window.open"
    assert sent["payload"]["window"] == "presentation:project-dashboard"
    assert sent["payload"]["data"] is _SLIDES


def test_open_presentation_slides_default_window():
    player, server = _make_player()
    player.open_presentation_slides(_SLIDES)
    assert _last_sent(server)["payload"]["window"] == "presentation"


def test_close_presentation_uses_window_kwarg():
    player, server = _make_player()
    player.close_presentation(window="presentation:foo")
    sent = _last_sent(server)
    assert sent["type"] == "window.close"
    assert sent["payload"]["window"] == "presentation:foo"


def test_close_presentation_default_window():
    player, server = _make_player()
    player.close_presentation()
    assert _last_sent(server)["payload"]["window"] == "presentation"


def test_advance_presentation_slide_uses_window_kwarg():
    player, server = _make_player()
    result = player.advance_presentation_slide(1, window="presentation:foo")
    sent = _last_sent(server)
    assert sent["type"] == "window.command"
    assert sent["payload"]["window"] == "presentation:foo"
    assert sent["payload"]["command"] == "advance"
    assert sent["payload"]["delta"] == 1
    assert result == "1"


def test_advance_presentation_slide_default_window():
    player, server = _make_player()
    player.advance_presentation_slide(-1)
    assert _last_sent(server)["payload"]["window"] == "presentation"


def test_open_presentation_uses_window_kwarg():
    player, server = _make_player()
    player.open_presentation("Hello", "body", window="presentation:hello")
    sent = _last_sent(server)
    assert sent["type"] == "window.open"
    assert sent["payload"]["window"] == "presentation:hello"


def test_update_presentation_uses_window_kwarg():
    player, server = _make_player()
    player.update_presentation("body", window="presentation:foo")
    sent = _last_sent(server)
    assert sent["type"] == "window.command"
    assert sent["payload"]["window"] == "presentation:foo"
    assert sent["payload"]["command"] == "update"