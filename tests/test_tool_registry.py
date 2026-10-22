from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from agent import tool_registry

def test_registry_populated():
    schemas = tool_registry.get_schemas()
    assert len(schemas) >= 20, f"Expected at least 20 tools, got {len(schemas)}"
    
    names = [s["name"] for s in schemas]
    assert "web_search" in names
    assert "open_app" in names
    assert "coding_workspace" in names


def test_has_tool_alias():
    assert tool_registry.has_tool("file_controller")
    assert not tool_registry.has_tool("nonexistent_xyz")

def test_is_registered():
    assert tool_registry.is_registered("web_search")
    assert not tool_registry.is_registered("non_existent_tool")

def test_dispatch_unknown_tool():
    with pytest.raises(KeyError, match="Unknown tool: non_existent_tool"):
        tool_registry.dispatch("non_existent_tool", {})

def test_dispatch_calls_handler():
    # Mock a tool
    mock_handler = MagicMock(return_value="Mock result")
    tool_registry.register("mock_tool", {"name": "mock_tool"}, mock_handler)
    
    result = tool_registry.dispatch("mock_tool", {"param": 1})
    
    assert result == "Mock result"
    mock_handler.assert_called_once_with(parameters={"param": 1}, player=None)


