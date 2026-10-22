"""Tests for the memory_recall tool dispatched through agent.tool_registry."""

from __future__ import annotations

import agent.tool_registry as tool_registry


def test_dispatch_returns_recalled_memories(monkeypatch):
    # Arrange
    assert tool_registry.is_registered("memory_recall")
    monkeypatch.setattr(
        "memory.semantic_memory.recall",
        lambda query, k=3: ["[fact] test memory"],
    )

    # Act
    result = tool_registry.dispatch("memory_recall", {"query": "anything"})

    # Assert
    assert "test memory" in result


def test_missing_query_returns_guidance_without_raising():
    # Arrange
    from actions.memory_recall import memory_recall

    # Act
    result = memory_recall(parameters={})

    # Assert
    assert isinstance(result, str)
    assert result == "What should I search my memories for?"


def test_handler_swallows_recall_exception(monkeypatch):
    # Arrange
    def boom(query, k=3):
        raise RuntimeError("recall exploded")

    monkeypatch.setattr("memory.semantic_memory.recall", boom)

    # Act
    result = tool_registry.dispatch("memory_recall", {"query": "anything"})

    # Assert
    assert isinstance(result, str)
    assert "went wrong" in result


class _FakePlayer:
    def __init__(self):
        self.open_calls: list[dict] = []

    def open_memories(self, payload: dict) -> None:
        self.open_calls.append(payload)


def test_browse_action_opens_memories_window():
    # Arrange
    from actions.memory_recall import memory_recall

    player = _FakePlayer()

    # Act
    result = memory_recall(parameters={"action": "browse"}, player=player)

    # Assert
    assert player.open_calls == [{}]
    assert "opening" in result.lower()


def test_browse_action_without_player_returns_graceful_string():
    # Arrange
    from actions.memory_recall import memory_recall

    # Act (player defaults to None; also exercises case/whitespace normalisation)
    result = memory_recall(parameters={"action": "  BROWSE  "})

    # Assert
    assert isinstance(result, str)
    assert "web UI" in result
