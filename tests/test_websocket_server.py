"""Tests for core/websocket_server — the Screen Watch soft-disconnect toggle.

Screen Watch live streaming is not wired in this build (v1): toggling watch ON
must broadcast an 'inactive' status and must NOT leave the internal bool True.
The screen_watch property/setter stays for UI compatibility.
"""

from __future__ import annotations

import asyncio

from core.websocket_server import WebSocketPlayer, WebSocketServer


class _FakePlayer:
    def __init__(self):
        self.muted = False
        self.screen_watch = False
        self.on_text_command = None
        self.on_screen_watch_changed = None

    def _setup_todo_listener(self):
        pass


def _make_server(monkeypatch, player=None):
    player = player or _FakePlayer()
    server = WebSocketServer(player=player)
    sent: list[dict] = []
    monkeypatch.setattr(server, "send", lambda msg: sent.append(msg))
    return server, player, sent


def test_toggle_watch_on_soft_disconnects(monkeypatch):
    server, player, sent = _make_server(monkeypatch)
    asyncio.run(server._dispatch({"type": "command.toggle_watch", "payload": {}}))
    assert sent == [{"type": "status.update", "payload": {"watch": "inactive"}}]
    assert player.screen_watch is False


def test_toggle_watch_off_from_active(monkeypatch):
    player = _FakePlayer()
    player.screen_watch = True
    server, player, sent = _make_server(monkeypatch, player=player)
    asyncio.run(server._dispatch({"type": "command.toggle_watch", "payload": {}}))
    assert player.screen_watch is False
    assert sent == []  # setter broadcasts via player path


def test_screen_watch_property_still_works(monkeypatch):
    server = WebSocketServer(player=_FakePlayer())
    sent: list[dict] = []
    monkeypatch.setattr(server, "send", lambda msg: sent.append(msg))
    player = WebSocketPlayer(server)
    assert player.screen_watch is False
    player.screen_watch = True
    assert player.screen_watch is True
    assert sent[-1] == {"type": "status.update", "payload": {"watch": "active"}}
    player.screen_watch = False
    assert player.screen_watch is False
    assert sent[-1] == {"type": "status.update", "payload": {"watch": "inactive"}}
