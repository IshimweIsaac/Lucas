"""Tests for core/opencode/opencode_api.py — relay/gate/workspace methods.

These tests never touch the real OpenCode server or memory/opencode_live.json;
the ``OpenCodeAPI`` methods are exercised with a fake ``OpenCodeClient`` wired in
via monkeypatched module imports.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import core.opencode.opencode_api as oc_api
from core.opencode.opencode_client import OpenCodeError


@pytest.fixture()
def fake_client() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def api(fake_client, monkeypatch) -> oc_api.OpenCodeAPI:
    """OpenCodeAPI instance whose server-bound imports point at a fake client."""

    def _get_client(*_args, **_kwargs):
        return fake_client

    def _ensure_server(*_args, **_kwargs):
        return fake_client

    monkeypatch.setattr(oc_api, "get_client", _get_client)
    monkeypatch.setattr(oc_api, "ensure_server", _ensure_server)
    return oc_api.OpenCodeAPI()


class TestQuestionsList:
    def test_questions_list_formats_pending(self, api, fake_client):
        fake_client.list_questions.return_value = [
            {"id": "q1", "question": "Continue?", "sessionID": "ses_1"},
        ]
        result = api.questions_list()
        assert "[questions_list] OK" in result
        assert "q1" in result
        assert "Continue?" in result
        assert "ses_1" in result

    def test_questions_list_empty(self, api, fake_client):
        fake_client.list_questions.return_value = []
        result = api.questions_list()
        assert "no pending questions" in result

    def test_questions_list_error(self, api, fake_client):
        fake_client.list_questions.side_effect = OpenCodeError("down")
        result = api.questions_list()
        assert "[questions_list] ERROR" in result


class TestQuestionAsk:
    def test_question_ask_with_answer_calls_reply_question(self, api, fake_client):
        fake_client.reply_question.return_value = True
        result = api.question_ask("q1", "yes")
        assert "[question_ask] OK" in result
        fake_client.reply_question.assert_called_once_with("q1", answers=["yes"])

    def test_question_ask_relay_returns_first_question(self, api, fake_client):
        fake_client.list_questions.return_value = [
            {"id": "q1", "question": "Continue?", "sessionID": "ses_1"},
        ]
        result = api.question_ask()
        assert "[question_ask] RELAY" in result
        assert "q1" in result
        assert "Continue?" in result

    def test_question_ask_relay_none(self, api, fake_client):
        fake_client.list_questions.return_value = []
        result = api.question_ask()
        assert "no pending questions" in result


class TestAnswerQuestion:
    def test_answer_question_calls_client(self, api, fake_client):
        fake_client.reply_question.return_value = True
        result = api.answer_question("q1", "yes")
        assert "[answer_question] OK" in result
        fake_client.reply_question.assert_called_once_with("q1", answers=["yes"])

    def test_answer_question_missing_params(self, api):
        result = api.answer_question("", "")
        assert "[answer_question] ERROR" in result


class TestQuestionReject:
    def test_question_reject_calls_client(self, api, fake_client):
        fake_client.reject_question.return_value = True
        result = api.question_reject("q1")
        assert "[question_reject] OK" in result
        fake_client.reject_question.assert_called_once_with("q1")

    def test_question_reject_missing(self, api):
        result = api.question_reject("")
        assert "[question_reject] ERROR" in result


class TestPermissionsList:
    def test_permissions_list_formats(self, api, fake_client):
        fake_client.list_permissions.return_value = [
            {"id": "per_1", "description": "edit file", "sessionID": "ses_1"},
        ]
        result = api.permissions_list()
        assert "[permissions_list] OK" in result
        assert "per_1" in result
        assert "edit file" in result

    def test_permissions_list_empty(self, api, fake_client):
        fake_client.list_permissions.return_value = []
        result = api.permissions_list()
        assert "no pending permissions" in result


class TestPermissionApprove:
    def test_approve_global_per(self, api, fake_client):
        fake_client.reply_permission.return_value = True
        result = api.permission_approve("per_1", permission="once")
        assert "[approve] OK" in result
        fake_client.reply_permission.assert_called_once_with("per_1", reply="once")

    def test_approve_session_scoped(self, api, fake_client):
        fake_client.reply_session_permission.return_value = True
        result = api.permission_approve("req_1", session_id="ses_1")
        assert "[approve] OK" in result
        fake_client.reply_session_permission.assert_called_once_with(
            "ses_1", "req_1", response="allow"
        )

    def test_approve_no_pending(self, api, fake_client):
        fake_client.list_permissions.return_value = []
        result = api.permission_approve("")
        assert "[approve] ERROR" in result


class TestPermissionDeny:
    def test_deny_global_per(self, api, fake_client):
        fake_client.reply_permission.return_value = True
        result = api.permission_deny("per_1")
        assert "[deny] OK" in result
        fake_client.reply_permission.assert_called_once_with("per_1", reply="reject")

    def test_deny_session_scoped(self, api, fake_client):
        fake_client.reply_session_permission.return_value = True
        result = api.permission_deny("req_1", session_id="ses_1")
        assert "[deny] OK" in result
        fake_client.reply_session_permission.assert_called_once_with(
            "ses_1", "req_1", response="reject"
        )


class TestSessionDiffRevert:
    def test_session_diff_formats(self, api, fake_client):
        fake_client.session_diff.return_value = [
            {"path": "a.py", "status": "modified"},
        ]
        result = api.session_diff("ses_1")
        assert "[diff] OK" in result
        assert "a.py" in result

    def test_session_diff_no_session(self, api, monkeypatch):
        monkeypatch.setattr(oc_api, "get_active_session", lambda: "")
        result = api.session_diff("")
        assert "[diff] ERROR" in result

    def test_session_revert_calls_client(self, api, fake_client):
        fake_client.session_revert.return_value = True
        result = api.session_revert("ses_1")
        assert "[revert] OK" in result
        fake_client.session_revert.assert_called_once_with("ses_1", message_id="")


class TestWorkspace:
    def test_workspace_list_formats_servers(self, api, monkeypatch):
        monkeypatch.setattr(
            oc_api, "list_servers",
            lambda: [
                {"workspace": "/tmp/x", "running": True, "port": 1234},
            ],
        )
        result = api.workspace_list()
        assert "[list_workspace] OK" in result
        assert "/tmp/x" in result

    def test_workspace_set_valid(self, api, monkeypatch, tmp_path):
        called: list = []

        def _fake_ensure(ws):
            called.append(str(ws))
            return MagicMock()

        monkeypatch.setattr(oc_api, "ensure_server", _fake_ensure)
        result = api.workspace_set(str(tmp_path))
        assert "[set_workspace] OK" in result
        assert str(tmp_path.resolve()) in result
        assert called

    def test_workspace_set_missing_dir_returns_error(self, api, tmp_path):
        result = api.workspace_set(str(tmp_path / "nope"))
        assert "[set_workspace] ERROR" in result

    def test_workspace_switch_ok(self, api, monkeypatch, tmp_path):
        monkeypatch.setattr(oc_api, "ensure_server", lambda ws: MagicMock())
        result = api.workspace_switch(str(tmp_path))
        assert "[switch_workspace] OK" in result

    def test_workspace_switch_missing_dir_returns_error(self, api, tmp_path):
        result = api.workspace_switch(str(tmp_path / "nope"))
        assert "[switch_workspace] ERROR" in result
