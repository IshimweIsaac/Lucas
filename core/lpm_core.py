"""Lucas Project Management — local JSON-backed PM system."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_LPM_DIR = Path(__file__).resolve().parent.parent / "memory" / "lpm"
_PROJECTS_FILE = _LPM_DIR / "projects.json"
_TASKS_FILE = _LPM_DIR / "tasks.json"
_LABELS_FILE = _LPM_DIR / "labels.json"
_SPRINTS_FILE = _LPM_DIR / "sprints.json"


def _ensure_dirs() -> None:
    _LPM_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to load %s: %s", path, exc)
    return []


def _save_json(path: Path, data: list[dict]) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── PROJECTS ──


def create_project(name: str, description: str = "") -> str:
    """Create a new project. Returns a human-readable result string."""
    projects = _load_json(_PROJECTS_FILE)
    pid = f"proj-{len(projects) + 1}"
    projects.append(
        {
            "id": pid,
            "name": name,
            "description": description,
            "created": datetime.now().isoformat(),
            "status": "active",
        }
    )
    _save_json(_PROJECTS_FILE, projects)
    return f"Project created: {name} ({pid})"


def list_projects(status: str = "") -> str:
    """List all projects, optionally filtered by status."""
    projects = _load_json(_PROJECTS_FILE)
    if status:
        projects = [p for p in projects if p.get("status") == status]
    if not projects:
        return "No projects found."
    lines = [
        f"  {p['name']} ({p['id']}) — {p.get('status', 'active')}" for p in projects
    ]
    return "Projects:\n" + "\n".join(lines)


def get_project(project_id: str) -> str:
    """Show details for a single project including task counts."""
    projects = _load_json(_PROJECTS_FILE)
    for p in projects:
        if p["id"] == project_id:
            tasks = _load_json(_TASKS_FILE)
            project_tasks = [t for t in tasks if t.get("project_id") == project_id]
            done = sum(1 for t in project_tasks if t.get("status") == "done")
            return (
                f"Project: {p['name']}\n"
                f"  Description: {p.get('description', 'N/A')}\n"
                f"  Status: {p.get('status', 'active')}\n"
                f"  Tasks: {len(project_tasks)} total, {done} done"
            )
    return f"Project not found: {project_id}"


def delete_project(project_id: str) -> str:
    """Delete a project by ID."""
    projects = _load_json(_PROJECTS_FILE)
    new_projects = [p for p in projects if p["id"] != project_id]
    if len(new_projects) == len(projects):
        return f"Project not found: {project_id}"
    _save_json(_PROJECTS_FILE, new_projects)
    return f"Project deleted: {project_id}"


def project_stats() -> str:
    """Return overall project stats."""
    projects = _load_json(_PROJECTS_FILE)
    tasks = _load_json(_TASKS_FILE)
    total = len(projects)
    active = sum(1 for p in projects if p.get("status") == "active")
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.get("status") == "done")
    return (
        f"LPM Stats: {total} projects ({active} active), "
        f"{total_tasks} tasks ({done_tasks} done)"
    )


# ── TASKS ──


def create_task(
    project_id: str,
    name: str,
    description: str = "",
    priority: str = "medium",
    labels: str = "",
    due_date: str = "",
) -> str:
    """Create a task in a project. Returns a human-readable result string."""
    projects = _load_json(_PROJECTS_FILE)
    if not any(p["id"] == project_id for p in projects):
        return f"Project not found: {project_id}"
    tasks = _load_json(_TASKS_FILE)
    tid = f"task-{len(tasks) + 1}"
    tasks.append(
        {
            "id": tid,
            "project_id": project_id,
            "name": name,
            "description": description,
            "priority": priority,
            "labels": [lb.strip() for lb in labels.split(",") if lb.strip()],
            "due_date": due_date,
            "status": "todo",
            "created": datetime.now().isoformat(),
        }
    )
    _save_json(_TASKS_FILE, tasks)
    return f"Task created: {name} ({tid}) in project {project_id}"


def list_tasks(
    project_id: str = "",
    status: str = "",
    priority: str = "",
) -> str:
    """List tasks, optionally filtered by project, status, or priority."""
    tasks = _load_json(_TASKS_FILE)
    if project_id:
        tasks = [t for t in tasks if t.get("project_id") == project_id]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if priority:
        tasks = [t for t in tasks if t.get("priority") == priority]
    if not tasks:
        return "No tasks found."
    lines = []
    for t in tasks:
        p = t.get("priority", "medium")
        icon = {
            "urgent": "RED",
            "high": "ORANGE",
            "medium": "YELLOW",
            "low": "GREEN",
        }.get(p, "WHITE")
        status_icon = {
            "todo": "○",
            "in_progress": "◐",
            "done": "●",
            "cancelled": "✕",
        }.get(t.get("status", "todo"), "○")
        lines.append(f"  {status_icon} [{icon}] {t['name']} ({t['id']})")
    return f"Tasks ({len(tasks)}):\n" + "\n".join(lines)


def update_task(task_id: str, **kwargs: str | None) -> str:
    """Update one or more fields of a task."""
    tasks = _load_json(_TASKS_FILE)
    for t in tasks:
        if t["id"] == task_id:
            for k, v in kwargs.items():
                if v is not None and v != "":
                    t[k] = v
            _save_json(_TASKS_FILE, tasks)
            return f"Task updated: {t['name']} ({task_id})"
    return f"Task not found: {task_id}"


def delete_task(task_id: str) -> str:
    """Delete a task by ID."""
    tasks = _load_json(_TASKS_FILE)
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return f"Task not found: {task_id}"
    _save_json(_TASKS_FILE, new_tasks)
    return f"Task deleted: {task_id}"


def board_view(project_id: str = "") -> str:
    """Kanban-style board grouped by status."""
    tasks = _load_json(_TASKS_FILE)
    if project_id:
        tasks = [t for t in tasks if t.get("project_id") == project_id]
    if not tasks:
        return "No tasks to show."
    groups: dict[str, list[str]] = {
        "todo": [],
        "in_progress": [],
        "done": [],
        "cancelled": [],
    }
    for t in tasks:
        groups.get(t.get("status", "todo"), []).append(t["name"])
    lines: list[str] = []
    for status, items in groups.items():
        if items:
            lines.append(f"\n  [{status.upper()}]")
            for item in items:
                lines.append(f"    - {item}")
    return "Board:" + "".join(lines)


# ── LABELS ──


def create_label(name: str, color: str = "#3388ff") -> str:
    """Create a new label."""
    labels = _load_json(_LABELS_FILE)
    lid = f"label-{len(labels) + 1}"
    labels.append({"id": lid, "name": name, "color": color})
    _save_json(_LABELS_FILE, labels)
    return f"Label created: {name} ({lid})"


def list_labels() -> str:
    """List all labels."""
    labels = _load_json(_LABELS_FILE)
    if not labels:
        return "No labels created."
    return "Labels:\n" + "\n".join(f"  {lb['name']} ({lb['id']})" for lb in labels)


def delete_label(label_id: str) -> str:
    """Delete a label by ID."""
    labels = _load_json(_LABELS_FILE)
    new_labels = [lb for lb in labels if lb["id"] != label_id]
    if len(new_labels) == len(labels):
        return f"Label not found: {label_id}"
    _save_json(_LABELS_FILE, new_labels)
    return f"Label deleted: {label_id}"
