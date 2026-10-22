"""Tests for actions/opencode_control.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions import opencode_control as oc


def test_tool_schema_has_required_fields():
    """TOOL_SCHEMA must contain name, description, and parameters block."""
    assert oc.TOOL_SCHEMA["name"] == "opencode_control"
    assert "description" in oc.TOOL_SCHEMA
    params = oc.TOOL_SCHEMA["parameters"]
    assert params["type"] == "OBJECT"
    assert "action" in params["properties"]
    assert "action" in params.get("required", [])


def test_tool_schema_properties():
    """Every declared action must be in the enum list."""
    enum_actions = oc.TOOL_SCHEMA["parameters"]["properties"]["action"]["enum"]
    expected = [
        "send", "task", "status", "cancel", "spawn",
        "trace", "jobs_list", "session_list",
        "find", "read_file", "open_window", "close_window",
        "question_ask", "answer_question", "reject_question", "questions_list",
        "approve", "deny", "permissions_list",
        "diff", "revert",
        "set_workspace", "list_workspace", "switch_workspace",
    ]
    for e in expected:
        assert e in enum_actions, f"Missing action: {e}"
    assert len(enum_actions) == len(set(enum_actions)), "Duplicate actions in enum"


def test_empty_action_returns_error():
    """Calling with no action must return an ERROR message."""
    result = oc.opencode_control(parameters={})
    assert "[opencode_control] ERROR" in result


def test_unknown_action_returns_error():
    """An unrecognized action must return an UNKNOWN message."""
    result = oc.opencode_control(parameters={"action": "fly_to_moon"})
    assert "UNKNOWN" in result


def test_send_no_goal_returns_error():
    """send action without a goal must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "send"})
    assert "[send] ERROR" in result
    assert "No goal" in result


def test_task_no_goal_returns_error():
    """task action without a goal must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "task"})
    assert "[task] ERROR" in result
    assert "No goal" in result


def test_find_no_query_returns_error():
    """find action without a query must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "find"})
    assert "[find] ERROR" in result
    assert "No query" in result


def test_read_file_no_path_returns_error():
    """read_file action without file_path must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "read_file"})
    assert "[read_file] ERROR" in result
    assert "No file_path" in result


def test_spawn_no_goal_returns_error():
    """spawn action without a goal must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "spawn"})
    assert "[spawn] ERROR" in result
    assert "No goal" in result


def test_dedup_rejects_duplicate():
    """Sending the same goal twice within the dedup window must be rejected."""
    oc._last_send.clear()

    # Mock OpenCodeAPI so the send call is instant (no real server interaction)
    mock_api = MagicMock()
    mock_api.send.return_value = "[send] STARTED\n\nworkspace: /tmp"

    goal = "Fix the login form validation"
    params = {"action": "send", "goal": goal}

    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        # First call should submit
        r1 = oc.opencode_control(parameters=params)
        assert "[send] SUBMITTED" in r1

        # Second immediate call should dedup
        r2 = oc.opencode_control(parameters=params)
        assert "[send] DEDUP" in r2


def test_dedup_allows_different_goals():
    """Different goals should not trigger dedup."""
    oc._last_send.clear()

    mock_api = MagicMock()
    mock_api.send.return_value = "[send] STARTED\n\nworkspace: /tmp"

    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        r1 = oc.opencode_control(parameters={"action": "send", "goal": "Goal A"})
        assert "[send] SUBMITTED" in r1

        r2 = oc.opencode_control(parameters={"action": "send", "goal": "Goal B"})
        assert "[send] SUBMITTED" in r2


def test_status_handles_exception():
    """If OpenCodeAPI.status raises, the handler must return an ERROR."""
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI",
        side_effect=RuntimeError("Server down"),
    ):
        result = oc._handle_status("")
        assert "[status] ERROR" in result
        assert "Server down" in result


def test_jobs_list_handles_exception():
    """If OpenCodeAPI.jobs_list raises, the handler must return an ERROR."""
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI",
        side_effect=RuntimeError("No jobs"),
    ):
        result = oc._handle_jobs_list()
        assert "[jobs_list] ERROR" in result
        assert "No jobs" in result


def test_open_window_delegates_to_api():
    """open_window action should delegate to OpenCodeAPI.open_window."""
    mock_api = MagicMock()
    mock_api.open_window.return_value = "[open_window] OK\n\nTracker opened."

    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "open_window", "goal": "My tracker"}
        )
        assert "[open_window] OK" in result


def test_close_window_delegates_to_api():
    """close_window action should delegate to OpenCodeAPI.close_window."""
    mock_api = MagicMock()
    mock_api.close_window.return_value = "[close_window] OK\n\nWindow closed."

    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "close_window", "token": "abc123"}
        )
        assert "[close_window] OK" in result


def test_answer_question_delegates_to_api():
    """answer_question should delegate to OpenCodeAPI.answer_question."""
    mock_api = MagicMock()
    mock_api.answer_question.return_value = (
        "[answer_question] OK\n\nReplied to q1: yes"
    )
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "answer_question", "request_id": "q1", "answer": "yes"}
        )
        assert "[answer_question] OK" in result
        mock_api.answer_question.assert_called_once_with("q1", "yes")


def test_answer_question_missing_params_returns_error():
    """answer_question without request_id or answer must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "answer_question", "answer": "x"})
    assert "[answer_question] ERROR" in result
    assert "request_id" in result
    result = oc.opencode_control(parameters={"action": "answer_question", "request_id": "q1"})
    assert "[answer_question] ERROR" in result


def test_reject_question_delegates_to_api():
    """reject_question should delegate to OpenCodeAPI.question_reject."""
    mock_api = MagicMock()
    mock_api.question_reject.return_value = "[question_reject] OK\n\nRejected q1."
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "reject_question", "request_id": "q1"}
        )
        assert "[question_reject] OK" in result
        mock_api.question_reject.assert_called_once_with("q1")


def test_reject_question_missing_request_id_returns_error():
    """reject_question without request_id must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "reject_question"})
    assert "[reject_question] ERROR" in result


def test_question_ask_delegates_to_api():
    """question_ask action should delegate to OpenCodeAPI.question_ask."""
    mock_api = MagicMock()
    mock_api.question_ask.return_value = "[question_ask] RELAY\n\nrequest_id: q1\nOpenCode asks: continue?"
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "question_ask", "request_id": "q1"}
        )
        assert "[question_ask] RELAY" in result
        mock_api.question_ask.assert_called_once_with("q1", "")


def test_questions_list_delegates_to_api():
    """questions_list action should delegate to OpenCodeAPI.questions_list."""
    mock_api = MagicMock()
    mock_api.questions_list.return_value = "[questions_list] OK\n\n- q1: continue?"
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(parameters={"action": "questions_list"})
        assert "[questions_list] OK" in result
        mock_api.questions_list.assert_called_once_with()


def test_approve_delegates_to_api():
    """approve action should delegate to OpenCodeAPI.permission_approve."""
    mock_api = MagicMock()
    mock_api.permission_approve.return_value = "[approve] OK\n\nApproved per_1."
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "approve", "request_id": "per_1"}
        )
        assert "[approve] OK" in result
        mock_api.permission_approve.assert_called_once_with(
            "per_1", session_id="", permission="once"
        )


def test_deny_delegates_to_api():
    """deny action should delegate to OpenCodeAPI.permission_deny."""
    mock_api = MagicMock()
    mock_api.permission_deny.return_value = "[deny] OK\n\nDenied per_1."
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "deny", "request_id": "per_1"}
        )
        assert "[deny] OK" in result
        mock_api.permission_deny.assert_called_once_with("per_1", session_id="")


def test_permissions_list_delegates_to_api():
    """permissions_list action delegates to OpenCodeAPI.permissions_list."""
    mock_api = MagicMock()
    mock_api.permissions_list.return_value = "[permissions_list] OK\n\n- per_1: edit file"
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(parameters={"action": "permissions_list"})
        assert "[permissions_list] OK" in result


def test_set_workspace_delegates_to_api():
    """set_workspace action delegates to OpenCodeAPI.workspace_set."""
    mock_api = MagicMock()
    mock_api.workspace_set.return_value = "[set_workspace] OK\n\nactive workspace: /tmp/x"
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "set_workspace", "workspace_path": "/tmp/x"}
        )
        assert "[set_workspace] OK" in result
        mock_api.workspace_set.assert_called_once_with("/tmp/x")


def test_set_workspace_missing_path_returns_error():
    """set_workspace without workspace_path must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "set_workspace"})
    assert "[set_workspace] ERROR" in result
    assert "workspace_path" in result


def test_switch_workspace_missing_path_returns_error():
    """switch_workspace without workspace_path must return an ERROR."""
    result = oc.opencode_control(parameters={"action": "switch_workspace"})
    assert "[switch_workspace] ERROR" in result


def test_list_workspace_delegates_to_api():
    """list_workspace action delegates to OpenCodeAPI.workspace_list."""
    mock_api = MagicMock()
    mock_api.workspace_list.return_value = "[list_workspace] OK\n\nactive_workspace: /tmp/x"
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(parameters={"action": "list_workspace"})
        assert "[list_workspace] OK" in result


def test_switch_workspace_delegates_to_api():
    """switch_workspace action delegates to OpenCodeAPI.workspace_switch."""
    mock_api = MagicMock()
    mock_api.workspace_switch.return_value = "[switch_workspace] OK\n\nSwitched."
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI", return_value=mock_api
    ):
        result = oc.opencode_control(
            parameters={"action": "switch_workspace", "workspace_path": "/tmp/x"}
        )
        assert "[switch_workspace] OK" in result
        mock_api.workspace_switch.assert_called_once_with("/tmp/x")


def test_api_call_uniform_error_envelope():
    """_api_call should wrap exceptions in a labeled ERROR."""
    with patch(
        "core.opencode.opencode_api.OpenCodeAPI",
        side_effect=RuntimeError("boom"),
    ):
        result = oc.opencode_control(parameters={"action": "questions_list"})
        assert "[questions_list] ERROR" in result
        assert "boom" in result
