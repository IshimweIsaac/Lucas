"""LPM (Lucas Project Management) — voice-controllable project management.

All data is stored locally in memory/lpm/ JSON files.
When the LPM FastAPI backend (http://localhost:8765/api/v1/) is running,
actions delegate to the HTTP API with JSON file fallback.
"""

from __future__ import annotations

import httpx
from typing import Callable

from core.logger import get_logger
from core import lpm_core

logger = get_logger(__name__)

_API_BASE = "http://localhost:8765/api/v1"
_API_HEADERS = {"Authorization": "Bearer dev-key"}
_API_TIMEOUT = 5.0


# ── HTTP API helpers ──


def _api_call(
    method: str, path: str, json_body: dict | None = None
) -> dict | list | None:
    """Make HTTP call to LPM backend. Returns None on connection error."""
    try:
        with httpx.Client(
            base_url=_API_BASE, headers=_API_HEADERS, timeout=_API_TIMEOUT
        ) as client:
            resp = client.request(method, path, json=json_body)
            resp.raise_for_status()
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        return None


def _api(
    method: str,
    path: str,
    json_body: dict | None = None,
    fallback: Callable[[], str] | None = None,
) -> str:
    """Call LPM API with fallback. Returns a human-readable result string."""
    data = _api_call(method, path, json_body)
    if data is not None:
        return _format_api_result(method, path, data)
    if fallback:
        return fallback()
    return "LPM backend is not running."


def _format_api_result(method: str, path: str, data: dict | list) -> str:
    """Convert API response JSON into a speakable result string."""
    if isinstance(data, list):
        if not data:
            return "No results found."
        lines = []
        for item in data:
            name = item.get("name") or item.get("title") or item.get("id", "?")
            status = item.get("status", "")
            priority = item.get("priority", "")
            parts = [str(name)]
            if status:
                parts.append(f"[{status}]")
            if priority:
                parts.append(f"({priority})")
            lines.append("  - " + " ".join(parts))
        return f"Found {len(data)} items:\n" + "\n".join(lines)

    # Single object response
    if "error" in data:
        return f"Error: {data['error']}"

    name = data.get("name") or data.get("title") or data.get("id", "Item")
    msg_parts = []
    if method == "POST":
        msg_parts.append(f"Created: {name}")
    elif method == "PUT":
        msg_parts.append(f"Updated: {name}")
    elif method == "DELETE":
        msg_parts.append(f"Deleted: {name}")
    elif method == "GET":
        msg_parts.append(str(name))

    extra = []
    for key in ("status", "priority", "project"):
        val = data.get(key)
        if val:
            extra.append(f"{key}={val}")
    if extra:
        msg_parts.append(f" ({', '.join(extra)})")

    return "".join(msg_parts)


# ── Fallback helpers ──


def _update_task_fallback(task_id: str, parameters: dict) -> str:
    """Fallback for update_task using JSON-backed lpm_core."""
    kwargs: dict[str, str | None] = {}
    for field in ("name", "description", "priority", "status", "labels", "due_date"):
        val = parameters.get(field)
        if val is not None:
            kwargs[field] = str(val) if val != "" else None
    return lpm_core.update_task(task_id, **kwargs)


def _move_task_fallback(task_id: str, status: str) -> str:
    """Fallback for move_task — just update status via lpm_core."""
    return lpm_core.update_task(task_id, status=status)


def _state_fallback() -> str:
    """Fallback for project_status — combine project+task stats."""
    return lpm_core.project_stats()


# ── Specialized formatters ──


def _format_sprint_health(data: dict | list) -> str:
    """Format sprint health data into a speakable summary."""
    if isinstance(data, list):
        return _format_api_result("GET", "state/Sprint", data)
    name = data.get("name") or data.get("id", "Sprint")
    status = data.get("status", "unknown")
    total = data.get("total_tasks", 0)
    done = data.get("done_tasks", 0)
    blocked = data.get("blocked_tasks", 0)
    risk = data.get("risk_level", "low")
    pct = f"{int(done / total * 100)}%" if total else "N/A"
    return (
        f"Sprint {name} is {status}. "
        f"Progress: {done}/{total} tasks done ({pct}). "
        f"Blocked: {blocked}. Risk: {risk}."
    )


def _format_alerts(data: dict | list) -> str:
    """Format alerts into a speakable summary."""
    if isinstance(data, list):
        if not data:
            return "No alerts."
        lines = [
            f"Alert {i + 1}: {a.get('message', str(a))}" for i, a in enumerate(data)
        ]
        return "Alerts:\n" + "\n".join(lines)
    if "alerts" in data:
        return _format_alerts(data["alerts"])
    return str(data)


TOOL_SCHEMA = {
    "name": "lpm_control",
    "description": (
        "Lucas Project Management — manage projects, tasks, sprints, labels. "
        "Actions: create_project, list_projects, get_project, delete_project, "
        "project_stats, create_task, list_tasks, update_task, move_task, delete_task, "
        "get_task, board_view, create_sprint, list_sprints, show_my_tasks, "
        "sprint_health, blocked_tasks, project_status, alerts, "
        "create_label, list_labels, delete_label."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "create_project | list_projects | get_project | delete_project | "
                    "project_stats | create_task | list_tasks | update_task | move_task | "
                    "delete_task | get_task | board_view | create_sprint | list_sprints | "
                    "show_my_tasks | sprint_health | blocked_tasks | project_status | alerts | "
                    "create_label | list_labels | delete_label"
                ),
            },
            "project_id": {
                "type": "STRING",
                "description": "Project ID like proj-1 or project name",
            },
            "task_id": {
                "type": "STRING",
                "description": "Task ID like task-1",
            },
            "name": {
                "type": "STRING",
                "description": "Name for the project or task being created",
            },
            "title": {
                "type": "STRING",
                "description": "Title for a task (alternative to name)",
            },
            "description": {
                "type": "STRING",
                "description": "Description text",
            },
            "priority": {
                "type": "STRING",
                "description": "urgent | high | medium | low (default: medium)",
            },
            "status": {
                "type": "STRING",
                "description": "todo | in_progress | done | cancelled",
            },
            "assignee": {
                "type": "STRING",
                "description": "Assignee username for task",
            },
            "labels": {
                "type": "STRING",
                "description": "Comma-separated label names",
            },
            "due_date": {
                "type": "STRING",
                "description": "Due date string (free text)",
            },
            "label_name": {
                "type": "STRING",
                "description": "Name for a new label",
            },
            "label_id": {
                "type": "STRING",
                "description": "Label ID like label-1",
            },
            "color": {
                "type": "STRING",
                "description": "Hex color like #3388ff",
            },
        },
        "required": ["action"],
    },
}


def lpm_control(parameters: dict, player=None) -> str:
    """Execute an LPM action. Dispatches to HTTP API with JSON fallback."""
    action = (parameters.get("action") or "").lower().strip()
    if not action:
        return "No action specified. Use create_project, list_projects, etc."

    if player:
        player.write_log(f"[LPM] {action}")

    # ── Projects ────────────────────────────────────────────────────────
    if action == "create_project":
        name = (parameters.get("name") or "").strip()
        if not name:
            return "Missing required parameter: name"
        description = (parameters.get("description") or "").strip()
        body = {"name": name}
        if description:
            body["description"] = description
        return _api(
            "POST",
            "projects",
            body,
            fallback=lambda: lpm_core.create_project(name, description),
        )

    if action == "list_projects":
        status = (parameters.get("status") or "").strip()
        path = "projects"
        if status:
            path = f"projects?status={status}"
        return _api("GET", path, fallback=lambda: lpm_core.list_projects(status))

    if action == "get_project":
        project_id = (parameters.get("project_id") or "").strip()
        if not project_id:
            return "Missing required parameter: project_id"
        return _api(
            "GET",
            f"projects/{project_id}",
            fallback=lambda: lpm_core.get_project(project_id),
        )

    if action == "delete_project":
        project_id = (parameters.get("project_id") or "").strip()
        if not project_id:
            return "Missing required parameter: project_id"
        return _api(
            "DELETE",
            f"projects/{project_id}",
            fallback=lambda: lpm_core.delete_project(project_id),
        )

    if action == "project_status":
        return _api("GET", "state", fallback=lambda: _state_fallback())

    if action == "project_stats":
        return lpm_core.project_stats()

    # ── Tasks ───────────────────────────────────────────────────────────
    if action == "create_task":
        project_id = (parameters.get("project_id") or "").strip()
        name = (parameters.get("name") or parameters.get("title") or "").strip()
        if not project_id:
            return "Missing required parameter: project_id"
        if not name:
            return "Missing required parameter: name"
        description = (parameters.get("description") or "").strip()
        priority = (parameters.get("priority") or "medium").strip().lower()
        assignee = (parameters.get("assignee") or "").strip()
        due_date = (parameters.get("due_date") or "").strip()

        body: dict[str, str] = {"project": project_id, "title": name}
        if description:
            body["description"] = description
        if priority:
            body["priority"] = priority
        if assignee:
            body["assignee"] = assignee
        if due_date:
            body["due_date"] = due_date
        return _api(
            "POST",
            "tasks",
            body,
            fallback=lambda: lpm_core.create_task(
                project_id,
                name,
                description,
                priority,
                parameters.get("labels", "").strip(),
                due_date,
            ),
        )

    if action == "list_tasks":
        project_id = (parameters.get("project_id") or "").strip()
        status = (parameters.get("status") or "").strip()
        priority = (parameters.get("priority") or "").strip()
        assignee = (parameters.get("assignee") or "").strip()
        params_parts: list[str] = []
        if project_id:
            params_parts.append(f"project={project_id}")
        if status:
            params_parts.append(f"status={status}")
        if priority:
            params_parts.append(f"priority={priority}")
        if assignee:
            params_parts.append(f"assignee={assignee}")
        qs = "&".join(params_parts)
        path = f"tasks?{qs}" if qs else "tasks"
        return _api(
            "GET",
            path,
            fallback=lambda: lpm_core.list_tasks(project_id, status, priority),
        )

    if action == "update_task":
        task_id = (parameters.get("task_id") or "").strip()
        if not task_id:
            return "Missing required parameter: task_id"
        body: dict[str, str] = {}
        for field in (
            "name",
            "title",
            "description",
            "priority",
            "status",
            "assignee",
            "due_date",
        ):
            val = parameters.get(field)
            if val is not None and str(val).strip():
                api_key = "title" if field in ("name", "title") else field
                body[api_key] = str(val).strip()
        if not body:
            return f"No fields to update for task {task_id}"
        return _api(
            "PUT",
            f"tasks/{task_id}",
            body,
            fallback=lambda: _update_task_fallback(task_id, parameters),
        )

    if action == "move_task":
        task_id = (parameters.get("task_id") or "").strip()
        status = (parameters.get("status") or "").strip()
        if not task_id:
            return "Missing required parameter: task_id"
        if not status:
            return "Missing required parameter: status (e.g. done, in_progress)"
        return _api(
            "PUT",
            f"tasks/{task_id}",
            {"status": status},
            fallback=lambda: _move_task_fallback(task_id, status),
        )

    if action == "delete_task":
        task_id = (parameters.get("task_id") or "").strip()
        if not task_id:
            return "Missing required parameter: task_id"
        return _api(
            "DELETE", f"tasks/{task_id}", fallback=lambda: lpm_core.delete_task(task_id)
        )

    if action == "get_task":
        task_id = (parameters.get("task_id") or "").strip()
        if not task_id:
            return "Missing required parameter: task_id"
        return _api("GET", f"tasks/{task_id}")

    if action == "board_view":
        project_id = (parameters.get("project_id") or "").strip()
        return lpm_core.board_view(project_id)

    # ── Sprints ─────────────────────────────────────────────────────────
    if action == "create_sprint":
        name = (parameters.get("name") or "").strip()
        if not name:
            return "Missing required parameter: name"
        body: dict[str, str] = {"name": name}
        description = (parameters.get("description") or "").strip()
        if description:
            body["description"] = description
        result = _api_call("POST", "sprints", body)
        if result is not None:
            return _format_api_result("POST", "sprints", result)
        return "LPM backend is not running. Sprint management requires the backend."

    if action == "list_sprints":
        result = _api_call("GET", "sprints")
        if result is not None:
            return _format_api_result("GET", "sprints", result)
        return "LPM backend is not running. Sprint management requires the backend."

    # ── Queries ─────────────────────────────────────────────────────────
    if action == "show_my_tasks":
        assignee = (parameters.get("assignee") or "").strip()
        path = "tasks?assignee=me" if not assignee else f"tasks?assignee={assignee}"
        result = _api_call("GET", path)
        if result is not None:
            return _format_api_result("GET", path, result)
        name = assignee or "you"
        return f"Cannot fetch tasks for {name}. LPM backend is not running. Use list_tasks to see JSON-backed tasks."

    if action == "sprint_health":
        result = _api_call("GET", "state/Sprint")
        if result is not None:
            return _format_sprint_health(result)
        return "LPM backend is not running. Sprint health requires the backend."

    if action == "blocked_tasks":
        result = _api_call("GET", "tasks?is_blocked=true")
        if result is not None:
            return _format_api_result("GET", "tasks?is_blocked=true", result)
        return "LPM backend is not running. Use list_tasks to see JSON-backed tasks."

    if action == "alerts":
        result = _api_call("GET", "alerts")
        if result is not None:
            return _format_alerts(result)
        return "LPM backend is not running. Alerts require the backend."

    # ── Labels ──
    if action == "create_label":
        label_name = (parameters.get("label_name") or "").strip()
        if not label_name:
            return "Missing required parameter: label_name"
        color = (parameters.get("color") or "#3388ff").strip()
        return lpm_core.create_label(label_name, color)

    if action == "list_labels":
        return lpm_core.list_labels()

    if action == "delete_label":
        label_id = (parameters.get("label_id") or "").strip()
        if not label_id:
            return "Missing required parameter: label_id"
        return lpm_core.delete_label(label_id)

    return (
        f"Unknown action: {action}. "
        "Use: create_project, list_projects, get_project, delete_project, "
        "project_stats, create_task, list_tasks, update_task, move_task, "
        "delete_task, get_task, board_view, create_sprint, list_sprints, "
        "show_my_tasks, sprint_health, blocked_tasks, project_status, alerts, "
        "create_label, list_labels, delete_label."
    )
