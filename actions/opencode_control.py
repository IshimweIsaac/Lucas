"""Control OpenCode agents via voice commands.

Registered in ``agent/tool_registry.py`` as ``actions.opencode_control``
with ``accepts_speak=True``.
"""

from __future__ import annotations

import time

from core.logger import get_logger

logger = get_logger(__name__)

# -- dedup ------------------------------------------------------------------
# Prevent sending the same goal twice within 12 seconds.
_SEND_DEDUP_SEC = 12
_last_send: dict[str, float] = {}

TOOL_SCHEMA = {
    "name": "opencode_control",
    "description": (
        "Send tasks to OpenCode AI agents for coding, debugging, refactoring, "
        "and research. Use for complex multi-file coding work, debugging crashes, "
        "code review, architecture design, or any task requiring AI-assisted "
        "development."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to perform: send (execute general task), "
                    "task (structured coding task), status (check job status), "
                    "cancel (cancel running job), spawn (spawn specific agent), "
                    "trace (get job trace), trace_voice (get speakable trace summary), "
                    "trace_deep (recursive agent tree), "
                    "jobs_list (list all jobs), "
                    "session_list, find, read_file, open_window, close_window, "
                    "question_ask (relay a pending OpenCode question), "
                    "answer_question (submit the user's spoken answer), "
                    "reject_question (never mind), questions_list, "
                    "approve (allow a pending permission), deny (deny a pending permission), "
                    "permissions_list, diff (session diff), revert (session revert), "
                    "set_workspace, list_workspace, switch_workspace"
                ),
                "enum": [
                    "send", "task", "status", "cancel", "spawn",
                    "trace", "trace_voice", "trace_deep", "jobs_list", "session_list",
                    "find", "read_file", "open_window", "close_window",
                    "question_ask", "answer_question", "reject_question", "questions_list",
                    "approve", "deny", "permissions_list",
                    "diff", "revert",
                    "set_workspace", "list_workspace", "switch_workspace",
                ],
            },
            "goal": {
                "type": "STRING",
                "description": (
                    "Task description or goal. Be specific about what needs "
                    "to be done, which files, and expected outcome."
                ),
            },
            "agent": {
                "type": "STRING",
                "description": "Specific agent to spawn (for spawn action). Default: build",
            },
            "workspace_path": {
                "type": "STRING",
                "description": "Path to the project/repo directory. Default: ~/Documents/Lucas",
            },
            "query": {
                "type": "STRING",
                "description": "Search query for find action",
            },
            "file_path": {
                "type": "STRING",
                "description": "File path for read_file action",
            },
            "token": {
                "type": "STRING",
                "description": "Job token for status/cancel/trace actions",
            },
            "request_id": {
                "type": "STRING",
                "description": (
                    "Pending question/permission request id (from questions_list "
                    "or permissions_list)"
                ),
            },
            "answer": {
                "type": "STRING",
                "description": "User's spoken answer for answer_question",
            },
            "session_id": {
                "type": "STRING",
                "description": (
                    "Session id for session-scoped permission replies or diff/revert"
                ),
            },
            "permission": {
                "type": "STRING",
                "description": "Approve scope: once, always, reject, or session (default: once)",
            },
            "message_id": {
                "type": "STRING",
                "description": "Message id for diff/revert at a specific point",
            },
        },
        "required": ["action"],
    },
}


def _dedup_check(goal: str) -> tuple[bool, float]:
    """Return (is_duplicate, last_send_time).

    When *goal* was sent within the dedup window, returns ``(True, last)``
    where *last* is the original send timestamp. Otherwise stores the
    current time and returns ``(False, now)``.
    """
    now = time.time()
    last = _last_send.get(goal)
    if last is not None and now - last < _SEND_DEDUP_SEC:
        return True, last
    _last_send[goal] = now
    return False, now


# -- action handlers ---------------------------------------------------------


def _handle_send(goal: str, workspace: str, speak) -> str:
    if not goal:
        return "[send] ERROR\n\nNo goal provided. Specify what OpenCode should do."

    is_dup, last = _dedup_check(goal)
    if is_dup:
        now = time.time()
        return (
            f"[send] DEDUP\n\nSame goal sent {now - last:.0f}s ago "
            f"— ignoring duplicate."
        )

    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        api.send(goal=goal, workspace=workspace)
        return (
            f"[send] SUBMITTED\n\nTask submitted: {goal[:200]}"
        )
    except Exception as exc:
        logger.exception("opencode_control send failed")
        return f"[send] ERROR\n\n{str(exc)[:500]}"


def _handle_task(goal: str, workspace: str, speak) -> str:
    if not goal:
        return "[task] ERROR\n\nNo goal provided. Specify what OpenCode should do."

    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        api.task(goal=goal, workspace=workspace)
        return (
            f"[task] SUBMITTED\n\nStructured coding task: {goal[:200]}"
        )
    except Exception as exc:
        logger.exception("opencode_control task failed")
        return f"[task] ERROR\n\n{str(exc)[:500]}"


def _handle_status(token: str) -> str:
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.status()
    except Exception as exc:
        logger.exception("opencode_control status failed")
        return f"[status] ERROR\n\n{str(exc)[:500]}"


def _handle_cancel(token: str) -> str:
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.cancel(job_token=token)
    except Exception as exc:
        logger.exception("opencode_control cancel failed")
        return f"[cancel] ERROR\n\n{str(exc)[:500]}"


def _handle_spawn(agent_name: str, goal: str, workspace: str, speak) -> str:
    if not goal:
        return "[spawn] ERROR\n\nNo goal provided."

    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        api.spawn(goal=goal, workspace=workspace)
        return (
            f"[spawn] SUBMITTED\n\nAgent '{agent_name}' spawned: {goal[:200]}"
        )
    except Exception as exc:
        logger.exception("opencode_control spawn failed")
        return f"[spawn] ERROR\n\n{str(exc)[:500]}"




def _handle_trace_deep(token: str) -> str:
    """Fetch full agent tree including sub-sub-agents (recursive)."""
    try:
        from core.opencode.opencode_server import get_client

        client = get_client(require_running=False)
        from core.opencode import opencode_trace as oc_trace
        digest = oc_trace.format_digest(token or "")
        lines = []
        if digest:
            lines.append(digest)
        try:
            from core.opencode.opencode_jobs import list_jobs
            for job in list_jobs():
                if isinstance(job, dict):
                    sid = job.get("session_id", "")
                    if sid:
                        children = client.session_children(sid) or []
                        lines.append("")
                        lines.append(f"session {sid[:12]}... children ({len(children)}):")
                        _walk_children(client, children, lines, depth=1)
        except Exception:
            pass
        result = "\n".join(lines) if lines else "(no active trace)"
        return f"[trace_deep] OK\n\n{result}"
    except Exception as e:
        return f"[trace_deep] ERROR\n\n{str(e)[:500]}"


def _walk_children(client, children: list, lines: list, depth: int = 0) -> None:
    """Recursively walk sub-agent children to arbitrary depth."""
    prefix = "  " * depth
    for child in (children or []):
        if not isinstance(child, dict):
            continue
        cid = child.get("id") or child.get("sessionID") or "?"
        title = child.get("title") or child.get("name") or cid[:12]
        phase = child.get("phase") or child.get("status") or ""
        meta = f" ({phase})" if phase else ""
        lines.append(f"{prefix}\u00b7 {title}{meta}  [{cid[:10]}...]")
        try:
            grand = client.session_children(cid) if cid != "?" else []
            if grand:
                _walk_children(client, grand, lines, depth + 1)
        except Exception:
            pass


def _handle_trace_voice(token: str) -> str:
    """Format OpenCode trace for voice output — concise, speakable summary."""
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        trace_result = api.trace()

        # Parse the trace result and format for speech
        lines = []
        if "[trace] OK" in trace_result:
            trace_body = trace_result.replace("[trace] OK\n\n", "")
        else:
            return "There is no active OpenCode trace to report."

        # Extract key sections for speech
        has_subagents = False
        has_tools = False
        has_files = False
        has_todos = False

        for line in trace_body.split("\n"):
            line = line.strip()
            if line.startswith("goal:"):
                lines.append(f"The task was: {line[5:].strip()}")
            elif line.startswith("phase:"):
                phase_info = line[6:].strip()
                lines.append(f"Status: {phase_info}")
            elif line.startswith("sub-agents"):
                has_subagents = True
                lines.append(" agents spawned:")
            elif has_subagents and line.startswith("  ·"):
                agent_name = line[3:].strip().split("(")[0].strip()
                lines.append(f"  - {agent_name}")
            elif line.startswith("tools:"):
                has_tools = True
                lines.append(" Tools used:")
            elif has_tools and line.startswith("  ·"):
                tool_info = line[3:].strip()[:80]
                lines.append(f"  - {tool_info}")
            elif line.startswith("files changed:"):
                has_files = True
                lines.append(" Files modified:")
            elif has_files and line.startswith("  ·"):
                file_path = line[3:].strip()
                lines.append(f"  - {file_path}")
            elif line.startswith("todos:"):
                has_todos = True
                lines.append(" Tasks:")
            elif has_todos and line.startswith("  ·"):
                todo_info = line[3:].strip()[:60]
                lines.append(f"  - {todo_info}")
            elif line.startswith("errors:"):
                lines.append(" Errors encountered:")
            elif line.startswith("latest reply:"):
                reply = line[13:].strip()[:200]
                lines.append(f" Result: {reply}")

        if not lines:
            return "OpenCode has no trace data available."

        # Now also try to get deep agent tree
        try:
            from core.opencode.opencode_jobs import list_jobs
            from core.opencode.opencode_server import get_client

            client = get_client(require_running=False)
            jobs = list_jobs()
            for job in jobs:
                if isinstance(job, dict):
                    sid = job.get("session_id", "")
                    if sid:
                        children = client.session_children(sid) or []
                        if children:
                            lines.append(" Full agent spawn tree:")
                            _walk_voice(client, children, lines, depth=0)
        except Exception:
            pass

        return "\\n".join(lines)
    except Exception as e:
        return f"Could not retrieve OpenCode trace: {str(e)[:200]}"


def _walk_voice(client, children: list, lines: list, depth: int = 0) -> None:
    """Walk sub-agent tree for voice output."""
    for child in (children or []):
        if not isinstance(child, dict):
            continue
        name = child.get("title") or child.get("name") or "agent"
        phase = child.get("phase") or child.get("status") or ""
        indent = "  " * depth
        if phase:
            lines.append(f"{indent} - {name} ({phase})")
        else:
            lines.append(f"{indent} - {name}")
        cid = child.get("id") or child.get("sessionID") or ""
        if cid:
            try:
                grand = client.session_children(cid) or []
                if grand:
                    _walk_voice(client, grand, lines, depth + 1)
            except Exception:
                pass


def _handle_trace(token: str) -> str:
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.trace()
    except Exception as exc:
        logger.exception("opencode_control trace failed")
        return f"[trace] ERROR\n\n{str(exc)[:500]}"


def _handle_jobs_list() -> str:
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.jobs_list()
    except Exception as exc:
        logger.exception("opencode_control jobs_list failed")
        return f"[jobs_list] ERROR\n\n{str(exc)[:500]}"


def _handle_session_list(workspace: str) -> str:
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.session_list(workspace=workspace)
    except Exception as exc:
        logger.exception("opencode_control session_list failed")
        return f"[session_list] ERROR\n\n{str(exc)[:500]}"


def _handle_find(query: str, workspace: str) -> str:
    if not query:
        return "[find] ERROR\n\nNo query provided."

    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.find(query, workspace=workspace)
    except Exception as exc:
        logger.exception("opencode_control find failed")
        return f"[find] ERROR\n\n{str(exc)[:500]}"


def _handle_read_file(file_path: str, workspace: str) -> str:
    if not file_path:
        return "[read_file] ERROR\n\nNo file_path provided."

    try:
        from core.opencode.opencode_api import OpenCodeAPI

        api = OpenCodeAPI()
        return api.read_file(file_path, workspace=workspace)
    except Exception as exc:
        logger.exception("opencode_control read_file failed")
        return f"[read_file] ERROR\n\n{str(exc)[:500]}"


# -- main entry point --------------------------------------------------------


def opencode_control(
    *, parameters: dict, player=None, speak=None
) -> str:
    """Execute OpenCode control action. Delegates to OpenCodeAPI."""
    action = (parameters.get("action") or "").lower().strip()
    goal = (parameters.get("goal") or "").strip()
    agent_name = (parameters.get("agent") or "").strip() or "build"
    workspace = (parameters.get("workspace_path") or "").strip() or "~/Documents/Lucas"
    query = (parameters.get("query") or "").strip()
    file_path = (parameters.get("file_path") or "").strip()
    token = (parameters.get("token") or "").strip()
    request_id = (parameters.get("request_id") or "").strip()
    answer = (parameters.get("answer") or "").strip()
    session_id = (parameters.get("session_id") or "").strip()
    permission = (parameters.get("permission") or "").strip() or "once"
    message_id = (parameters.get("message_id") or "").strip()

    if not action:
        return (
            "[opencode_control] ERROR\n\nNo action provided. "
            "Available: send, task, status, cancel, spawn, trace, trace_voice, "
            "trace_deep, jobs_list, session_list, find, read_file, "
            "open_window, close_window, question_ask, answer_question, "
            "reject_question, questions_list, approve, deny, permissions_list, "
            "diff, revert, set_workspace, list_workspace, switch_workspace"
        )

    if action == "send":
        return _handle_send(goal, workspace, speak)
    elif action == "task":
        return _handle_task(goal, workspace, speak)
    elif action == "status":
        return _handle_status(token)
    elif action == "cancel":
        return _handle_cancel(token)
    elif action == "spawn":
        return _handle_spawn(agent_name, goal, workspace, speak)
    elif action == "trace":
        return _handle_trace(token)
    elif action == "trace_voice":
        return _handle_trace_voice(token)
    elif action == "jobs_list":
        return _handle_jobs_list()
    elif action == "session_list":
        return _handle_session_list(workspace)
    elif action == "find":
        return _handle_find(query, workspace)
    elif action == "read_file":
        return _handle_read_file(file_path, workspace)
    elif action == "open_window":
        try:
            from core.opencode.opencode_api import OpenCodeAPI

            api = OpenCodeAPI()
            return api.open_window(goal=goal)
        except Exception as exc:
            logger.exception("opencode_control open_window failed")
            return f"[open_window] ERROR\n\n{str(exc)[:500]}"
    elif action == "close_window":
        try:
            from core.opencode.opencode_api import OpenCodeAPI

            api = OpenCodeAPI()
            return api.close_window(job_token=token, goal=goal)
        except Exception as exc:
            logger.exception("opencode_control close_window failed")
            return f"[close_window] ERROR\n\n{str(exc)[:500]}"
    elif action == "question_ask":
        return _api_call("question_ask", lambda api: api.question_ask(request_id, answer))
    elif action == "answer_question":
        if not request_id or not answer:
            return "[answer_question] ERROR\n\nrequest_id= and answer= required."
        return _api_call("answer_question", lambda api: api.answer_question(request_id, answer))
    elif action == "reject_question":
        if not request_id:
            return "[reject_question] ERROR\n\nrequest_id= required."
        return _api_call("reject_question", lambda api: api.question_reject(request_id))
    elif action == "questions_list":
        return _api_call("questions_list", lambda api: api.questions_list())
    elif action == "approve":
        return _api_call(
            "approve",
            lambda api: api.permission_approve(
                request_id, session_id=session_id, permission=permission
            ),
        )
    elif action == "deny":
        return _api_call(
            "deny",
            lambda api: api.permission_deny(request_id, session_id=session_id),
        )
    elif action == "permissions_list":
        return _api_call("permissions_list", lambda api: api.permissions_list())
    elif action == "diff":
        return _api_call(
            "diff",
            lambda api: api.session_diff(session_id, message_id=message_id),
        )
    elif action == "revert":
        return _api_call(
            "revert",
            lambda api: api.session_revert(session_id, message_id=message_id),
        )
    elif action == "set_workspace":
        if not (parameters.get("workspace_path") or "").strip():
            return "[set_workspace] ERROR\n\nworkspace_path= required."
        return _api_call("set_workspace", lambda api: api.workspace_set(workspace))
    elif action == "list_workspace":
        return _api_call("list_workspace", lambda api: api.workspace_list())
    elif action == "switch_workspace":
        if not (parameters.get("workspace_path") or "").strip():
            return "[switch_workspace] ERROR\n\nworkspace_path= required."
        return _api_call("switch_workspace", lambda api: api.workspace_switch(workspace))
    else:
        return (
            f"[opencode_control] UNKNOWN\n\nUnknown action: {action}. "
            "Available: send, task, status, cancel, spawn, trace, trace_voice, "
            "trace_deep, jobs_list, session_list, find, read_file, "
            "open_window, close_window, question_ask, answer_question, "
            "reject_question, questions_list, approve, deny, permissions_list, "
            "diff, revert, set_workspace, list_workspace, switch_workspace"
        )


def _api_call(label: str, fn) -> str:
    """Run an OpenCodeAPI call with a uniform error envelope."""
    try:
        from core.opencode.opencode_api import OpenCodeAPI

        return fn(OpenCodeAPI())
    except Exception as exc:
        logger.exception("opencode_control %s failed", label)
        return f"[{label}] ERROR\n\n{str(exc)[:500]}"
