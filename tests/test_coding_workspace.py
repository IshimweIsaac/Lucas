from __future__ import annotations

import json

import pytest

from actions import coding_workspace as cw
from agent import executor


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_path / "coding_profile.json")
    ws = tmp_path / "project"
    ws.mkdir()
    (ws / "main.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    return ws


def test_safe_path_rejects_escape(tmp_workspace):
    with pytest.raises(PermissionError):
        cw._safe_path(tmp_workspace, "../outside")


def test_apply_patch_single_match(tmp_workspace):
    msg = cw._apply_patch(tmp_workspace, "main.py", "return 1", "return 2")
    assert "Patched" in msg
    assert "return 2" in (tmp_workspace / "main.py").read_text(encoding="utf-8")


def test_apply_patch_zero_matches(tmp_workspace):
    msg = cw._apply_patch(tmp_workspace, "main.py", "return 99", "return 2")
    assert "not found" in msg.lower()


def test_apply_patch_multiple_matches(tmp_workspace):
    (tmp_workspace / "dup.py").write_text("x=1\nx=1\n", encoding="utf-8")
    msg = cw._apply_patch(tmp_workspace, "dup.py", "x=1", "x=2")
    assert "2 times" in msg


def test_apply_unified_diff(tmp_workspace):
    diff = """@@ -1,2 +1,2 @@
 def foo():
-    return 1
+    return 42
"""
    msg = cw._apply_patch(tmp_workspace, "main.py", diff=diff)
    assert "unified diff" in msg
    assert "return 42" in (tmp_workspace / "main.py").read_text(encoding="utf-8")


def test_read_file_numbered(tmp_workspace):
    out = cw._read_file(tmp_workspace, "main.py", 1, 2)
    assert "def foo" in out
    assert "1|" in out


def test_parse_agent_json_embedded():
    raw = 'Here is the action:\n{"action": "grep", "pattern": "foo"}'
    data = cw._parse_agent_json(raw)
    assert data["action"] == "grep"


def test_tree_cache(tmp_workspace):
    cw.invalidate_tree_cache()
    a = cw._get_cached_tree(tmp_workspace, depth=1)
    b = cw._get_cached_tree(tmp_workspace, depth=1)
    assert a == b


def test_run_verify_pass(tmp_workspace, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_workspace.parent / "coding_profile.json")
    prof = {"lint_command": "true", "verify_command": "true"}
    ok, out = cw._run_verify(tmp_workspace, prof)
    assert ok
    assert "VERIFY_OK" in out


def test_run_verify_fail(tmp_workspace):
    (tmp_workspace / "actions").mkdir()
    (tmp_workspace / "tests").mkdir()
    prof = {"lint_command": "false", "verify_command": "true"}
    ok, out = cw._run_verify(tmp_workspace, prof)
    assert not ok
    assert "VERIFY_FAILED" in out


def test_set_workspace_persists(tmp_workspace, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_workspace.parent / "coding_profile.json")
    result = cw.coding_workspace(
        {
            "action": "set_workspace",
            "workspace_path": str(tmp_workspace),
            "verify_command": "true",
            "lint_command": "true",
        }
    )
    assert "Workspace set" in result
    prof = json.loads((tmp_workspace.parent / "coding_profile.json").read_text(encoding="utf-8"))
    assert prof["verify_command"] == "true"


def test_executor_routes_coding_goal(monkeypatch):
    called = {}

    def fake_dispatch(name, parameters, **kwargs):
        called["name"] = name
        called["parameters"] = parameters
        return "routed"

    monkeypatch.setattr(executor.tool_registry, "dispatch", fake_dispatch)
    result = executor._call_tool(
        "generated_code",
        {"description": "fix the failing pytest in main.py"},
        None,
    )
    assert result == "routed"
    assert called["name"] == "coding_workspace"
    assert called["parameters"]["action"] == "task"


def test_workspace_supports_lint_lucas_repo(tmp_path):
    assert not cw._workspace_supports_lint(tmp_path)
    lucas_like = tmp_path / "proj"
    lucas_like.mkdir()
    (lucas_like / "tests").mkdir()
    (lucas_like / "actions").mkdir()
    assert cw._workspace_supports_lint(lucas_like)


def test_executor_skips_coding_route_for_non_code(monkeypatch):
    monkeypatch.setattr(
        executor,
        "_run_generated_code",
        lambda desc, speak=None: "generated",
    )
    result = executor._call_tool(
        "generated_code",
        {"description": "send an email to John about the meeting"},
        None,
    )
    assert result == "generated"


def test_profile_path_exists():
    assert cw.PROFILE_PATH.name == "coding_profile.json"


def test_lint_skipped_tests_only():
    assert cw._lint_skipped({"tests_only": True})
    assert cw._lint_skipped({"verify_mode": "tests_only"})
    assert not cw._lint_skipped({"verify_mode": "tests_and_lint", "tests_only": False})


def test_run_verify_tests_only_skips_lint(tmp_workspace):
    (tmp_workspace / "actions").mkdir()
    (tmp_workspace / "tests").mkdir()
    prof = {
        "tests_only": True,
        "lint_command": "false",
        "verify_command": "true",
    }
    ok, out = cw._run_verify(tmp_workspace, prof)
    assert ok
    assert "skipped" in out.lower()


def test_apply_patch_lines(tmp_workspace):
    (tmp_workspace / "main.py").write_text(
        "line1\nline2\nline3\nline4\n", encoding="utf-8"
    )
    msg = cw._apply_patch_lines(tmp_workspace, "main.py", 2, 3, "NEW\n")
    assert "Patched" in msg
    text = (tmp_workspace / "main.py").read_text(encoding="utf-8")
    assert "line1\nNEW\nline4" in text or text == "line1\nNEW\nline4\n"


def test_one_shot_executes_plan(tmp_workspace, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_workspace.parent / "coding_profile.json")
    (tmp_workspace / "main.py").write_text("x = 1\n", encoding="utf-8")
    prof = {"lint_command": "", "verify_command": "true", "tests_only": True}

    plan_json = json.dumps(
        {
            "steps": [
                {
                    "action": "patch_lines",
                    "path": "main.py",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "x = 2",
                }
            ]
        }
    )
    monkeypatch.setattr(cw, "_gemini_generate", lambda prompt: plan_json)
    result = cw._run_one_shot_task(
        "set x to 2",
        tmp_workspace,
        prof,
        "",
        "",
    )
    assert result is not None
    assert "one-shot" in result.lower()
    assert "x = 2" in (tmp_workspace / "main.py").read_text(encoding="utf-8")


def test_status_action(tmp_workspace, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_workspace.parent / "coding_profile.json")
    (tmp_workspace / "sample.py").write_text("x = 1\n", encoding="utf-8")
    cw.invalidate_tree_cache()
    cw._get_cached_tree(tmp_workspace, depth=1, refresh=True)

    result = cw.coding_workspace(
        {"action": "status", "workspace_path": str(tmp_workspace)}
    )

    assert str(tmp_workspace) in result
    assert "lint_command:" in result
    assert "verify_command:" in result
    assert "cached_tree_lines:" in result
    assert "sample.py" in cw._get_cached_tree(tmp_workspace, depth=1)


def test_run_with_command(tmp_workspace):
    result = cw.coding_workspace(
        {
            "action": "run",
            "workspace_path": str(tmp_workspace),
            "command": "true",
        }
    )
    assert result.startswith("OK")
    assert "exit_code: 0" in result


def test_run_without_command_uses_verify(tmp_workspace, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_workspace.parent / "coding_profile.json")
    prof = {"lint_command": "", "verify_command": "true", "tests_only": True}
    monkeypatch.setattr(cw, "_load_profile", lambda: prof)
    result = cw.coding_workspace(
        {"action": "run", "workspace_path": str(tmp_workspace)}
    )
    assert "VERIFY_OK" in result


def test_rust_workspace_skips_pytest(tmp_path):
    rust = tmp_path / "lumina"
    rust.mkdir()
    (rust / "Cargo.toml").write_text('[package]\nname = "lumina"\n', encoding="utf-8")
    prof = {"verify_command": "python -m pytest tests/ -q --tb=line"}
    assert cw._resolve_test_command(rust, prof) == "cargo check -q"


def test_set_workspace_rust_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "PROFILE_PATH", tmp_path / "coding_profile.json")
    rust = tmp_path / "lumina"
    rust.mkdir()
    (rust / "Cargo.toml").write_text('[package]\nname = "lumina"\n', encoding="utf-8")
    out = cw.coding_workspace(
        {"action": "set_workspace", "workspace_path": str(rust)}
    )
    assert "project: rust" in out
    prof = json.loads((tmp_path / "coding_profile.json").read_text(encoding="utf-8"))
    assert "cargo" in prof["verify_command"]

