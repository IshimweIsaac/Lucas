from __future__ import annotations

from agent.voice_routing import guard_tool_call


def test_blocks_computer_restart_for_lucas():
    out = guard_tool_call("computer_settings", {"description": "restart"})
    assert out is not None
    assert "restart_lucas" in out


def test_blocks_agent_task_for_reminder():
    out = guard_tool_call("agent_task", {"goal": "set a reminder for 3pm"})
    assert out is not None
    assert "direct tool" in out.lower()


def test_blocks_coding_task_small_edit():
    # action=task was removed from coding_workspace; the guard no longer blocks it
    out = guard_tool_call(
        "coding_workspace",
        {"action": "task", "goal": "fix the test in tests/test_foo.py"},
    )
    assert out is None


def test_blocks_computer_control_execute_for_time():
    out = guard_tool_call("computer_control", {"action": "execute", "command": "date"})
    assert out is not None
    assert "pc_controller" in out


def test_blocks_agent_task_for_time_question():
    out = guard_tool_call("agent_task", {"goal": "what is the current time right now"})
    assert out is not None
    assert "pc_controller" in out


def test_workspace_plural_routed_to_opencode():
    out = guard_tool_call("pc_controller", {"goal": "switch workspaces to the Lucas repo"})
    assert out is not None
    assert "opencode_control" in out
    assert "switch_workspace" in out


def test_workspace_singular_routed_to_opencode():
    out = guard_tool_call("agent_task", {"goal": "set workspace to /tmp/foo"})
    assert out is not None
    assert "opencode_control" in out


def test_fix_this_repo_routed_to_opencode():
    # agent_task is intercepted by an earlier repo-fix guard, so exercise the
    # new guard via pc_controller (which must not claim desktop workspace work).
    out = guard_tool_call("pc_controller", {"goal": "fix this repo"})
    assert out is not None
    assert "opencode_control" in out


def test_fix_single_file_not_routed_to_opencode():
    # "fix the test ..." must NOT match the workspace/repo fix guard.
    out = guard_tool_call("coding_workspace", {"action": "task", "goal": "fix the test in tests/test_foo.py"})
    assert out is None


def test_desktop_workspace_intent_routed_to_sway():
    # Desktop workspace switching (with a number) routes to sway_control,
    # not opencode_control (which owns the OpenCode coding workspace).
    out = guard_tool_call("pc_controller", {"goal": "switch to workspace 2"})
    assert out is not None
    assert "sway_control" in out


def test_desktop_workspace_intent_not_routed_to_opencode():
    # A bare "switch workspaces to <repo>" (no number) still routes to the
    # OpenCode coding workspace, not sway_control.
    out = guard_tool_call("pc_controller", {"goal": "switch workspaces to the lucas-repo-folder"})
    assert out is not None
    assert "opencode_control" in out


def test_sway_control_not_blocked_for_desktop_workspace():
    # The tool itself must be allowed through once the model picked sway_control.
    out = guard_tool_call("sway_control", {"goal": "switch to workspace 2"})
    assert out is None


def test_desktop_go_to_workspace_routed_to_sway():
    out = guard_tool_call("agent_task", {"goal": "go to the workspace 3"})
    assert out is not None
    assert "sway_control" in out


def test_present_on_workspace_not_bounced_from_presentation_control():
    # presentation_control has a `workspace` param that switches Sway before
    # opening, so "present on workspace 7" must NOT be redirected to sway_control.
    out = guard_tool_call("presentation_control", {"goal": "present on workspace 7"})
    assert out is None


def test_switch_workspace_bounced_from_presentation_control_to_sway():
    # Plain workspace switching (no present intent) still redirects to sway_control.
    out = guard_tool_call("presentation_control", {"goal": "switch to workspace 7"})
    assert out is not None
    assert "sway_control" in out


def test_present_on_workspace_with_sway_control_bounced_to_presentation():
    # When the model picked sway_control for a present intent, the presentation
    # guard still redirects to presentation_control (correct direction).
    out = guard_tool_call("sway_control", {"goal": "present on workspace 7"})
    assert out is not None
    assert "presentation_control" in out


def test_sway_control_passes_switch_workspace_guard():
    out = guard_tool_call("sway_control", {"goal": "switch to workspace 3"})
    assert out is None

