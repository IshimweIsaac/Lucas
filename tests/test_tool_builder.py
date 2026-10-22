from __future__ import annotations

import pytest

from actions import tool_builder as tb
from memory.custom_tools import loader as cl


@pytest.fixture
def custom_env(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"tools": []}', encoding="utf-8")
    monkeypatch.setattr(cl, "CUSTOM_DIR", tmp_path)
    monkeypatch.setattr(cl, "MANIFEST_PATH", manifest)
    return tmp_path


def test_validate_name_reserved():
    assert "reserved" in (tb._validate_name("tool_builder") or "")


def test_create_custom_tool(custom_env):
    msg = cl.add_custom_tool(
        "greet_test",
        "Says hello",
        "    name = (params.get('query') or 'sir').strip()\n    return f'Hello, {name}!'",
    )
    assert "Created custom tool" in msg
    script = custom_env / "greet_test.py"
    assert script.is_file()

    from agent import tool_registry

    cl.register_custom_tools(tool_registry.register)
    out = tool_registry.dispatch("greet_test", {"query": "Ada"})
    assert "Hello" in out and "Ada" in out


def test_tool_builder_list():
    out = tb.tool_builder({"action": "list"})
    assert "Registered tools" in out
