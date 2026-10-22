"""Tests for LPM (Lucas Project Management) — action module + core layer."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from actions.lpm_control import TOOL_SCHEMA, lpm_control
from core import lpm_core


# ── Helper ──


def _reset_lpm_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect LPM file paths to a temp directory for test isolation."""
    lpm_dir = tmp_path / "memory" / "lpm"
    lpm_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lpm_core, "_LPM_DIR", lpm_dir)
    monkeypatch.setattr(lpm_core, "_PROJECTS_FILE", lpm_dir / "projects.json")
    monkeypatch.setattr(lpm_core, "_TASKS_FILE", lpm_dir / "tasks.json")
    monkeypatch.setattr(lpm_core, "_LABELS_FILE", lpm_dir / "labels.json")


# ═══════════════════════════════════════════════════════════════════
# TOOL_SCHEMA structure
# ═══════════════════════════════════════════════════════════════════


class TestToolSchema:
    def test_schema_name(self):
        assert TOOL_SCHEMA["name"] == "lpm_control"

    def test_schema_has_description(self):
        assert len(TOOL_SCHEMA["description"]) > 20

    def test_schema_has_parameters(self):
        assert TOOL_SCHEMA["parameters"]["type"] == "OBJECT"

    def test_schema_action_required(self):
        assert "action" in TOOL_SCHEMA["parameters"]["required"]

    def test_schema_action_in_properties(self):
        assert "action" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_project_id_param(self):
        assert "project_id" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_task_id_param(self):
        assert "task_id" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_name_param(self):
        assert "name" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_priority_param(self):
        assert "priority" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_status_param(self):
        assert "status" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_label_name_param(self):
        assert "label_name" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_label_id_param(self):
        assert "label_id" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_color_param(self):
        assert "color" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_due_date_param(self):
        assert "due_date" in TOOL_SCHEMA["parameters"]["properties"]


# ═══════════════════════════════════════════════════════════════════
# Error handling — missing params
# ═══════════════════════════════════════════════════════════════════


class TestErrorHandling:
    def test_no_action_returns_error(self):
        result = lpm_control({})
        assert "No action specified" in result

    def test_unknown_action_returns_error(self):
        result = lpm_control({"action": "nonexistent"})
        assert "Unknown action" in result

    def test_create_project_missing_name(self):
        result = lpm_control({"action": "create_project"})
        assert "Missing required parameter: name" in result

    def test_get_project_missing_id(self):
        result = lpm_control({"action": "get_project"})
        assert "Missing required parameter: project_id" in result

    def test_delete_project_missing_id(self):
        result = lpm_control({"action": "delete_project"})
        assert "Missing required parameter: project_id" in result

    def test_create_task_missing_project_id(self):
        result = lpm_control({"action": "create_task"})
        assert "Missing required parameter: project_id" in result

    def test_create_task_missing_name(self):
        result = lpm_control({"action": "create_task", "project_id": "proj-1"})
        assert "Missing required parameter: name" in result

    def test_update_task_missing_id(self):
        result = lpm_control({"action": "update_task"})
        assert "Missing required parameter: task_id" in result

    def test_delete_task_missing_id(self):
        result = lpm_control({"action": "delete_task"})
        assert "Missing required parameter: task_id" in result

    def test_create_label_missing_name(self):
        result = lpm_control({"action": "create_label"})
        assert "Missing required parameter: label_name" in result

    def test_delete_label_missing_id(self):
        result = lpm_control({"action": "delete_label"})
        assert "Missing required parameter: label_id" in result


# ═══════════════════════════════════════════════════════════════════
# Project CRUD
# ═══════════════════════════════════════════════════════════════════


class TestProjectCrud:
    def test_create_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "create_project", "name": "TestApp"})
        assert "Project created: TestApp (proj-1)" in result

    def test_create_project_with_description(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "create_project",
                "name": "MyApp",
                "description": "A test project",
            }
        )
        assert "MyApp" in result

    def test_list_projects_after_create(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "Alpha"})
        lpm_control({"action": "create_project", "name": "Beta"})
        result = lpm_control({"action": "list_projects"})
        assert "Alpha" in result
        assert "Beta" in result
        assert "Projects:" in result

    def test_list_projects_empty(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "list_projects"})
        assert "No projects found." in result

    def test_get_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control(
            {"action": "create_project", "name": "MyApp", "description": "Desc"}
        )
        result = lpm_control({"action": "get_project", "project_id": "proj-1"})
        assert "MyApp" in result
        assert "Desc" in result
        assert "0 total, 0 done" in result

    def test_get_project_not_found(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "get_project", "project_id": "proj-99"})
        assert "Project not found: proj-99" in result

    def test_delete_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "Alpha"})
        result = lpm_control({"action": "delete_project", "project_id": "proj-1"})
        assert "Project deleted: proj-1" in result

    def test_delete_project_not_found(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "delete_project", "project_id": "proj-99"})
        assert "Project not found: proj-99" in result

    def test_project_stats(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "Alpha"})
        result = lpm_control({"action": "project_stats"})
        assert "1 projects (1 active)" in result
        assert "0 tasks (0 done)" in result


# ═══════════════════════════════════════════════════════════════════
# Task CRUD
# ═══════════════════════════════════════════════════════════════════


class TestTaskCrud:
    def test_create_task(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "MyApp"})
        result = lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Build login",
            }
        )
        assert "Task created: Build login (task-1)" in result

    def test_create_task_invalid_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-99",
                "name": "Do work",
            }
        )
        assert "Project not found: proj-99" in result

    def test_create_task_with_all_fields(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "MyApp"})
        result = lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Build feature",
                "description": "Implement the main feature",
                "priority": "high",
                "labels": "frontend,urgent",
                "due_date": "2026-07-15",
            }
        )
        assert "Task created: Build feature (task-1)" in result

    def test_list_tasks(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "MyApp"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task A",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task B",
            }
        )
        result = lpm_control({"action": "list_tasks"})
        assert "Task A" in result
        assert "Task B" in result
        assert "Tasks (2):" in result

    def test_list_tasks_empty(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "list_tasks"})
        assert "No tasks found." in result

    def test_list_tasks_filter_by_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_project", "name": "P2"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "P1 Task",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-2",
                "name": "P2 Task",
            }
        )
        result = lpm_control(
            {
                "action": "list_tasks",
                "project_id": "proj-1",
            }
        )
        assert "P1 Task" in result
        assert "P2 Task" not in result

    def test_list_tasks_filter_by_status(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "To do",
            }
        )
        lpm_control(
            {
                "action": "update_task",
                "task_id": "task-1",
                "status": "done",
            }
        )
        result = lpm_control(
            {
                "action": "list_tasks",
                "status": "done",
            }
        )
        assert "To do" in result
        result2 = lpm_control(
            {
                "action": "list_tasks",
                "status": "todo",
            }
        )
        assert "No tasks found." in result2

    def test_update_task(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task 1",
            }
        )
        result = lpm_control(
            {
                "action": "update_task",
                "task_id": "task-1",
                "status": "done",
            }
        )
        assert "Task updated: Task 1 (task-1)" in result

    def test_update_task_not_found(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "update_task",
                "task_id": "task-99",
                "status": "done",
            }
        )
        assert "Task not found: task-99" in result

    def test_delete_task(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task 1",
            }
        )
        result = lpm_control(
            {
                "action": "delete_task",
                "task_id": "task-1",
            }
        )
        assert "Task deleted: task-1" in result

    def test_delete_task_not_found(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "delete_task",
                "task_id": "task-99",
            }
        )
        assert "Task not found: task-99" in result

    def test_board_view(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task 1",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task 2",
            }
        )
        lpm_control(
            {
                "action": "update_task",
                "task_id": "task-2",
                "status": "done",
            }
        )
        result = lpm_control({"action": "board_view"})
        assert "Board:" in result
        assert "TODO" in result
        assert "DONE" in result

    def test_board_view_empty(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "board_view"})
        assert "No tasks to show." in result

    def test_board_view_filtered_by_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_project", "name": "P2"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "P1 Task",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-2",
                "name": "P2 Task",
            }
        )
        result = lpm_control(
            {
                "action": "board_view",
                "project_id": "proj-1",
            }
        )
        assert "P1 Task" in result
        assert "P2 Task" not in result


# ═══════════════════════════════════════════════════════════════════
# Label CRUD
# ═══════════════════════════════════════════════════════════════════


class TestLabelCrud:
    def test_create_label(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "create_label",
                "label_name": "bug",
            }
        )
        assert "Label created: bug (label-1)" in result

    def test_create_label_with_color(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "create_label",
                "label_name": "urgent",
                "color": "#ff0000",
            }
        )
        assert "Label created: urgent (label-1)" in result

    def test_list_labels(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_label", "label_name": "bug"})
        lpm_control({"action": "create_label", "label_name": "feature"})
        result = lpm_control({"action": "list_labels"})
        assert "bug" in result
        assert "feature" in result
        assert "Labels:" in result

    def test_list_labels_empty(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control({"action": "list_labels"})
        assert "No labels created." in result

    def test_delete_label(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_label", "label_name": "bug"})
        result = lpm_control(
            {
                "action": "delete_label",
                "label_id": "label-1",
            }
        )
        assert "Label deleted: label-1" in result

    def test_delete_label_not_found(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "delete_label",
                "label_id": "label-99",
            }
        )
        assert "Label not found: label-99" in result


# ═══════════════════════════════════════════════════════════════════
# Data persistence
# ═══════════════════════════════════════════════════════════════════


class TestDataPersistence:
    def test_project_persists_across_calls(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "PersistTest"})
        # Reload by calling list_projects (reads from file again)
        result = lpm_control({"action": "list_projects"})
        assert "PersistTest" in result

    def test_task_persists_in_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Persistent Task",
            }
        )
        # get_project shows task count
        result = lpm_control(
            {
                "action": "get_project",
                "project_id": "proj-1",
            }
        )
        assert "1 total" in result

    def test_label_persists_across_calls(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_label", "label_name": "docs"})
        result = lpm_control({"action": "list_labels"})
        assert "docs" in result

    def test_deleted_project_gone(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "Temp"})
        lpm_control({"action": "delete_project", "project_id": "proj-1"})
        result = lpm_control({"action": "list_projects"})
        assert "No projects found." in result

    def test_multiple_tasks_same_project(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "T1",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "T2",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "T3",
            }
        )
        result = lpm_control({"action": "list_tasks", "project_id": "proj-1"})
        assert "Tasks (3):" in result


# ═══════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_create_project_whitespace_name(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        result = lpm_control(
            {
                "action": "create_project",
                "name": "   ",
            }
        )
        assert "Missing required parameter: name" in result

    def test_create_task_whitespace_name(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        result = lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "   ",
            }
        )
        assert "Missing required parameter: name" in result

    def test_task_priority_icon_in_list(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Urgent task",
                "priority": "urgent",
            }
        )
        result = lpm_control({"action": "list_tasks"})
        assert "[RED]" in result
        assert "Urgent task" in result

    def test_stats_after_operations(self, tmp_path, monkeypatch):
        _reset_lpm_files(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_project", "name": "P2"})
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "T1",
            }
        )
        lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-2",
                "name": "T2",
            }
        )
        lpm_control(
            {
                "action": "update_task",
                "task_id": "task-1",
                "status": "done",
            }
        )
        result = lpm_control({"action": "project_stats"})
        assert "2 projects (2 active)" in result
        assert "2 tasks (1 done)" in result


# ═══════════════════════════════════════════════════════════════════
# HTTP API — mocked
# ═══════════════════════════════════════════════════════════════════


class _MockResponse:
    """Fake httpx.Response for testing."""

    def __init__(self, status_code: int, json_data: dict | list):
        self._status_code = status_code
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self._status_code >= 400:
            raise httpx.HTTPStatusError("Mock error", request=None, response=self)

    def json(self) -> dict | list:
        return self._json_data


class _MockClient:
    """Fake httpx.Client that returns canned responses."""

    def __init__(self, *, base_url="", headers=None, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def request(self, method: str, path: str, **kwargs) -> _MockResponse:
        if "error" in path:
            return _MockResponse(404, {"error": "not found"})
        if "sprints" in path:
            if method == "POST":
                return _MockResponse(
                    201,
                    {
                        "id": "sprint-1",
                        "name": kwargs.get("json", {}).get("name", "Sprint"),
                    },
                )
            return _MockResponse(
                200, [{"id": "sprint-1", "name": "Sprint 1", "status": "active"}]
            )
        if "state/Sprint" in path:
            return _MockResponse(
                200,
                {
                    "name": "Sprint 1",
                    "status": "active",
                    "total_tasks": 10,
                    "done_tasks": 6,
                    "blocked_tasks": 1,
                    "risk_level": "low",
                },
            )
        if "state" in path:
            return _MockResponse(
                200,
                {
                    "projects": 3,
                    "tasks": 15,
                    "done_tasks": 8,
                    "active_sprints": 1,
                },
            )
        if "alerts" in path:
            return _MockResponse(
                200,
                [
                    {"message": "Task overdue: Fix login"},
                    {"message": "Sprint ends tomorrow"},
                ],
            )
        if "tasks" in path:
            if "is_blocked" in path:
                return _MockResponse(
                    200,
                    [
                        {
                            "id": "task-3",
                            "name": "Blocked API",
                            "status": "in_progress",
                            "priority": "high",
                        },
                    ],
                )
            if "assignee" in path:
                return _MockResponse(
                    200,
                    [
                        {"id": "task-1", "name": "My Task", "status": "todo"},
                    ],
                )
            if method == "POST":
                body = kwargs.get("json", {})
                return _MockResponse(
                    201,
                    {
                        "id": "task-5",
                        "title": body.get("title", "Task"),
                        "status": "todo",
                    },
                )
            if method == "PUT":
                return _MockResponse(
                    200,
                    {
                        "id": path.split("/")[-1],
                        "title": "Updated Task",
                        "status": "done",
                    },
                )
            if method == "DELETE":
                return _MockResponse(200, {"id": path.split("/")[-1], "deleted": True})
            if method == "GET":
                # List all tasks
                if path.rstrip("/") == "tasks" or "?" in path:
                    return _MockResponse(
                        200,
                        [
                            {
                                "id": "task-1",
                                "name": "Task One",
                                "status": "todo",
                                "priority": "high",
                            },
                            {
                                "id": "task-2",
                                "name": "Task Two",
                                "status": "done",
                                "priority": "medium",
                            },
                        ],
                    )
                # GET single task by ID
                return _MockResponse(
                    200,
                    {
                        "id": path.split("/")[-1],
                        "title": "Single Task",
                        "status": "todo",
                    },
                )
        if "projects" in path:
            if method == "POST":
                body = kwargs.get("json", {})
                return _MockResponse(
                    201,
                    {
                        "id": "proj-1",
                        "name": body.get("name", "Project"),
                        "status": "active",
                    },
                )
            if method == "GET":
                if path == "projects":
                    return _MockResponse(
                        200,
                        [
                            {"id": "proj-1", "name": "Alpha", "status": "active"},
                            {"id": "proj-2", "name": "Beta", "status": "active"},
                        ],
                    )
                pid = path.split("/")[-1]
                return _MockResponse(
                    200, {"id": pid, "name": "Project Detail", "status": "active"}
                )
            if method == "DELETE":
                return _MockResponse(200, {"id": path.split("/")[-1], "deleted": True})
        return _MockResponse(200, {"ok": True})


class TestHttpApi:
    """Test HTTP-backed actions with a mocked httpx client."""

    @pytest.fixture(autouse=True)
    def _mock_httpx(self, monkeypatch: pytest.MonkeyPatch):
        """Replace httpx.Client with _MockClient for all tests in this class."""
        monkeypatch.setattr(httpx, "Client", _MockClient)

    # ── TOOL_SCHEMA has new params ──

    def test_schema_has_assignee_param(self):
        assert "assignee" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_has_title_param(self):
        assert "title" in TOOL_SCHEMA["parameters"]["properties"]

    def test_schema_description_mentions_new_actions(self):
        desc = TOOL_SCHEMA["description"]
        assert "move_task" in desc
        assert "show_my_tasks" in desc
        assert "sprint_health" in desc
        assert "blocked_tasks" in desc
        assert "alerts" in desc
        assert "create_sprint" in desc

    def test_schema_action_enum_mentions_new_actions(self):
        desc = TOOL_SCHEMA["parameters"]["properties"]["action"]["description"]
        assert "move_task" in desc
        assert "show_my_tasks" in desc
        assert "sprint_health" in desc
        assert "blocked_tasks" in desc
        assert "alerts" in desc
        assert "create_sprint" in desc

    # ── Project actions via HTTP ──

    def test_create_project_http(self):
        result = lpm_control({"action": "create_project", "name": "HTTP App"})
        assert "Created" in result

    def test_list_projects_http(self):
        result = lpm_control({"action": "list_projects"})
        assert "Found" in result
        assert "Alpha" in result

    def test_get_project_http(self):
        result = lpm_control({"action": "get_project", "project_id": "proj-1"})
        assert "Project Detail" in result

    def test_delete_project_http(self):
        result = lpm_control({"action": "delete_project", "project_id": "proj-1"})
        assert "Deleted" in result

    def test_project_status_http(self):
        result = lpm_control({"action": "project_status"})
        assert result != "LPM backend is not running."

    # ── Task actions via HTTP ──

    def test_create_task_http(self):
        result = lpm_control(
            {"action": "create_task", "project_id": "proj-1", "name": "Build feature"}
        )
        assert "Created" in result
        # Also test with assignee
        result2 = lpm_control(
            {
                "action": "create_task",
                "project_id": "proj-1",
                "name": "Task",
                "assignee": "me",
            }
        )
        assert "Created" in result2

    def test_list_tasks_http(self):
        result = lpm_control({"action": "list_tasks"})
        assert "Found" in result or "No" in result

    def test_list_tasks_filtered_http(self):
        result = lpm_control(
            {"action": "list_tasks", "project_id": "proj-1", "status": "todo"}
        )
        assert "Found" in result or "No" in result

    def test_update_task_http(self):
        result = lpm_control(
            {"action": "update_task", "task_id": "task-1", "status": "done"}
        )
        assert "Updated" in result

    def test_move_task_http(self):
        result = lpm_control(
            {"action": "move_task", "task_id": "task-1", "status": "done"}
        )
        assert "Updated" in result

    def test_move_task_missing_status(self):
        result = lpm_control({"action": "move_task", "task_id": "task-1"})
        assert "Missing required parameter" in result

    def test_delete_task_http(self):
        result = lpm_control({"action": "delete_task", "task_id": "task-1"})
        assert "Deleted" in result

    def test_get_task_http(self):
        result = lpm_control({"action": "get_task", "task_id": "task-1"})
        assert "Single Task" in result

    # ── Sprint actions ──

    def test_create_sprint_http(self):
        result = lpm_control({"action": "create_sprint", "name": "Sprint Alpha"})
        assert "Created" in result

    def test_create_sprint_missing_name(self):
        result = lpm_control({"action": "create_sprint"})
        assert "Missing required parameter: name" in result

    def test_list_sprints_http(self):
        result = lpm_control({"action": "list_sprints"})
        assert "Found" in result
        assert "Sprint 1" in result

    # ── Query actions ──

    def test_show_my_tasks_http(self):
        result = lpm_control({"action": "show_my_tasks"})
        assert "My Task" in result

    def test_show_my_tasks_with_assignee(self):
        result = lpm_control({"action": "show_my_tasks", "assignee": "john"})
        assert "John" in result or "Found" in result

    def test_sprint_health_http(self):
        result = lpm_control({"action": "sprint_health"})
        assert "Sprint" in result
        assert "6/10" in result or "60%" in result

    def test_blocked_tasks_http(self):
        result = lpm_control({"action": "blocked_tasks"})
        assert "Blocked API" in result

    def test_alerts_http(self):
        result = lpm_control({"action": "alerts"})
        assert "Alerts" in result or "Alert" in result


# ═══════════════════════════════════════════════════════════════════
# HTTP API — fallback on connection error
# ═══════════════════════════════════════════════════════════════════


class TestHttpFallback:
    """When HTTP backend is unreachable, fall back to JSON-backed lpm_core."""

    def _setup_lpm(self, tmp_path, monkeypatch):
        """Set up temp LPM files and ensure HTTP calls fail (default behavior)."""
        _reset_lpm_files(tmp_path, monkeypatch)
        # Don't mock httpx — real Client will get ConnectError

    def test_create_project_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "create_project", "name": "FallbackProj"})
        assert "Project created: FallbackProj (proj-1)" in result

    def test_list_projects_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "list_projects"})
        assert "No projects found." in result

    def test_create_task_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        result = lpm_control(
            {"action": "create_task", "project_id": "proj-1", "name": "FallbackTask"}
        )
        assert "Task created: FallbackTask (task-1)" in result

    def test_update_task_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_task", "project_id": "proj-1", "name": "T1"})
        result = lpm_control(
            {"action": "update_task", "task_id": "task-1", "status": "done"}
        )
        assert "Task updated" in result
        assert "T1" in result

    def test_move_task_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_task", "project_id": "proj-1", "name": "T1"})
        result = lpm_control(
            {"action": "move_task", "task_id": "task-1", "status": "done"}
        )
        assert "Task updated" in result

    def test_delete_task_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        lpm_control({"action": "create_task", "project_id": "proj-1", "name": "T1"})
        result = lpm_control({"action": "delete_task", "task_id": "task-1"})
        assert "Task deleted: task-1" in result

    def test_get_project_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        result = lpm_control({"action": "get_project", "project_id": "proj-1"})
        assert "P1" in result

    def test_delete_project_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        result = lpm_control({"action": "delete_project", "project_id": "proj-1"})
        assert "Project deleted: proj-1" in result

    def test_project_status_fallback(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        lpm_control({"action": "create_project", "name": "P1"})
        result = lpm_control({"action": "project_status"})
        assert "1 projects (1 active)" in result

    def test_sprint_actions_no_backend(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "create_sprint", "name": "NoBackendSprint"})
        assert "not running" in result

        result2 = lpm_control({"action": "list_sprints"})
        assert "not running" in result2

        result3 = lpm_control({"action": "sprint_health"})
        assert "not running" in result3

    def test_show_my_tasks_no_backend(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "show_my_tasks"})
        assert "not running" in result

    def test_blocked_tasks_no_backend(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "blocked_tasks"})
        assert "not running" in result

    def test_alerts_no_backend(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "alerts"})
        assert "not running" in result

    def test_get_task_no_backend(self, tmp_path, monkeypatch):
        self._setup_lpm(tmp_path, monkeypatch)
        result = lpm_control({"action": "get_task", "task_id": "task-1"})
        assert "not running" in result
