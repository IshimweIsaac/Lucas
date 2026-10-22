"""Tests for websocket_server memory.* handlers (Upgrade C backend).

Drives ``WebSocketServer._dispatch`` directly against an isolated semantic
memory DB (LUCAS_SEMANTIC_DB + module reload) and captures every broadcast by
monkeypatching ``server._broadcast`` with an async collector.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest

import memory.semantic_memory as semantic_memory
from core.websocket_server import WebSocketServer


@pytest.fixture()
def ws_sm(tmp_path, monkeypatch):
    """Reload semantic_memory with an isolated DB path; restore afterwards."""
    monkeypatch.setenv("LUCAS_SEMANTIC_DB", str(tmp_path / "sem.db"))
    reloaded = importlib.reload(semantic_memory)
    yield reloaded
    if reloaded._conn is not None:
        reloaded._conn.close()
    monkeypatch.delenv("LUCAS_SEMANTIC_DB", raising=False)
    importlib.reload(semantic_memory)


def _stub_embed(sm, monkeypatch) -> None:
    """Replace the network embedder with a tiny deterministic vector."""
    monkeypatch.setattr(sm, "embed_text", lambda text: [1.0, 0.0])


def _make_server(
    monkeypatch,
) -> tuple[WebSocketServer, list[dict[str, Any]]]:
    """Player-less server whose broadcasts land in an ordered list.

    ``_broadcast`` receives either a dict (dispatch handlers) or a JSON
    string (legacy callers); the collector normalises both to dicts.
    """
    server = WebSocketServer(player=None)
    sent: list[dict[str, Any]] = []

    async def _collector(data: Any) -> None:
        if isinstance(data, dict):
            sent.append(data)
        else:
            sent.append(json.loads(str(data)))

    monkeypatch.setattr(server, "_broadcast", _collector)
    return server, sent


def _dispatch(server: WebSocketServer, msg: dict[str, Any]) -> None:
    asyncio.run(server._dispatch(msg))


# ---------------------------------------------------------------------------
# memory.list
# ---------------------------------------------------------------------------


def test_memory_list_broadcasts_rows_total_and_echoes_query(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    ws_sm.remember("Unrelated grocery note")
    server, sent = _make_server(monkeypatch)

    # Act
    _dispatch(server, {"type": "memory.list", "payload": {"query": "cat"}})

    # Assert
    assert len(sent) == 1
    msg = sent[0]
    assert msg["type"] == "memory.data"
    payload = msg["payload"]
    assert set(payload.keys()) == {"memories", "total", "query"}
    assert payload["query"] == "cat"
    assert payload["total"] == 1
    assert len(payload["memories"]) == 1
    row = payload["memories"][0]
    assert set(row.keys()) == {"id", "text", "kind", "created_at"}
    assert "Pixel" in row["text"]


def test_memory_list_malformed_payload_types_still_serve_data(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    ws_sm.remember("Unrelated grocery note")
    server, sent = _make_server(monkeypatch)

    variants = [
        {"type": "memory.list", "payload": "junk"},
        {"type": "memory.list", "payload": None},
        {"type": "memory.list", "payload": {"limit": "abc"}},
        {"type": "memory.list", "payload": {"offset": None}},
    ]
    for variant in variants:
        # Act (must not raise)
        before = len(sent)
        _dispatch(server, variant)

        # Assert: coerced defaults still serve every seeded row
        data = sent[before]
        assert data["type"] == "memory.data"
        assert len(data["payload"]["memories"]) == 2
        assert data["payload"]["total"] == 2


# ---------------------------------------------------------------------------
# memory.delete
# ---------------------------------------------------------------------------


def test_memory_delete_ok_replies_result_then_broadcasts_fresh_data(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    ws_sm.remember("Unrelated grocery note")
    row_id = next(
        r["id"] for r in ws_sm.list_memories() if "Pixel" in r["text"]
    )
    server, sent = _make_server(monkeypatch)

    # Act
    _dispatch(server, {"type": "memory.delete", "payload": {"id": row_id}})

    # Assert: result ack first, fresh snapshot second, in order
    assert [m["type"] for m in sent] == ["memory.result", "memory.data"]
    result = sent[0]["payload"]
    assert result["ok"] is True
    assert result["id"] == row_id
    data = sent[1]["payload"]
    assert data["total"] == 1
    assert all(r["id"] != row_id for r in data["memories"])


@pytest.mark.parametrize(
    ("bad_payload",),
    [
        ({},),
        ({"id": "42"},),
        ({"id": 4.5},),
        ({"id": True},),
    ],
)
def test_memory_delete_missing_or_bad_id_returns_ok_false_without_raise(
    ws_sm, monkeypatch, bad_payload
):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    server, sent = _make_server(monkeypatch)

    for bad in bad_payload:
        # Act (must not raise)
        before = len(sent)
        _dispatch(server, {"type": "memory.delete", "payload": bad})

        # Assert
        result = sent[before]
        assert result["type"] == "memory.result"
        assert result["payload"]["ok"] is False
        assert result["payload"]["id"] is None
        assert result["payload"]["error"]
    assert len(ws_sm.list_memories()) == 1  # seed row survived every attempt


def test_memory_delete_second_time_returns_ok_false(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    row_id = ws_sm.list_memories()[0]["id"]
    server, sent = _make_server(monkeypatch)

    # Act
    _dispatch(server, {"type": "memory.delete", "payload": {"id": row_id}})
    _dispatch(server, {"type": "memory.delete", "payload": {"id": row_id}})

    # Assert: first ok:true (+data), second ok:false without another broadcast
    assert sent[0]["payload"]["ok"] is True
    assert [m["type"] for m in sent] == ["memory.result", "memory.data", "memory.result"]
    second = sent[-1]["payload"]
    assert second["ok"] is False
    assert second["id"] == row_id
    assert second["error"]


# ---------------------------------------------------------------------------
# memory.update
# ---------------------------------------------------------------------------


def test_memory_update_ok_replies_and_broadcasts(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    row_id = ws_sm.list_memories()[0]["id"]
    server, sent = _make_server(monkeypatch)

    # Act
    _dispatch(server, {
        "type": "memory.update",
        "payload": {"id": row_id, "text": "My dog is named Blaze"},
    })

    # Assert
    assert [m["type"] for m in sent] == ["memory.result", "memory.data"]
    assert sent[0]["payload"] == {"ok": True, "id": row_id}
    texts = [r["text"] for r in sent[1]["payload"]["memories"]]
    assert texts == ["My dog is named Blaze"]


@pytest.mark.parametrize(("bad_text",), [("",), ("   ",), (123,)])
def test_memory_update_empty_or_nonstr_text_returns_ok_false(
    ws_sm, monkeypatch, bad_text
):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("My cat is named Pixel")
    row_id = ws_sm.list_memories()[0]["id"]
    server, sent = _make_server(monkeypatch)

    # Act (must not raise)
    _dispatch(server, {
        "type": "memory.update",
        "payload": {"id": row_id, "text": bad_text},
    })

    # Assert
    assert len(sent) == 1
    result = sent[0]["payload"]
    assert result["ok"] is False
    assert result["id"] == row_id
    assert "non-empty" in result["error"]
    assert ws_sm.list_memories()[0]["text"] == "My cat is named Pixel"


# ---------------------------------------------------------------------------
# context reuse + socket safety
# ---------------------------------------------------------------------------


def test_post_mutation_broadcast_reuses_last_list_context(ws_sm, monkeypatch):
    # Arrange: browse a filtered view, then delete a row outside that filter
    _stub_embed(ws_sm, monkeypatch)
    ws_sm.remember("User writes Rust code every weekend")
    ws_sm.remember("User adopted a cat named Pixel")
    rows = {r["text"]: r["id"] for r in ws_sm.list_memories()}
    cat_id = rows["User adopted a cat named Pixel"]
    server, sent = _make_server(monkeypatch)

    # Act
    _dispatch(server, {"type": "memory.list", "payload": {"query": "rust"}})
    _dispatch(server, {"type": "memory.delete", "payload": {"id": cat_id}})

    # Assert: post-delete snapshot honours the last list query, read fresh
    final_data = sent[-1]
    assert final_data["type"] == "memory.data"
    payload = final_data["payload"]
    assert payload["query"] == "rust"
    assert [r["text"] for r in payload["memories"]] == [
        "User writes Rust code every weekend",
    ]
    assert payload["total"] == 1


def test_handlers_never_raise_on_non_dict_payload(ws_sm, monkeypatch):
    # Arrange
    _stub_embed(ws_sm, monkeypatch)
    server, sent = _make_server(monkeypatch)

    messages: list[dict[str, Any]] = [
        {"type": "memory.delete"},                # no payload key at all
        {"type": "memory.delete", "payload": None},
        {"type": "memory.update", "payload": "junk"},
        {"type": "memory.update"},                # no payload key at all
    ]
    for msg in messages:
        # Act (must not raise)
        _dispatch(server, msg)

    # Assert: each malformed request got a structured failure reply
    assert len(sent) == len(messages)
    for msg in sent:
        assert msg["type"] == "memory.result"
        assert msg["payload"]["ok"] is False
        assert msg["payload"]["error"]
