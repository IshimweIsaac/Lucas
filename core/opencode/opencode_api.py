"""OpenCode facade — workspace in, message to build agent, STARTED out."""

from __future__ import annotations

import re
from pathlib import Path

from core.opencode import opencode_background as oc_bg
from core.opencode import opencode_flow as oc_flow
from core.opencode import opencode_jobs as oc_jobs
from core.opencode.opencode_client import OpenCodeError
from core.opencode.opencode_defaults import DEFAULT_AGENT, DEFAULT_MODEL
from core.opencode.opencode_server import (
    ensure_server,
    get_active_session,
    get_client,
    list_servers,
    load_state,
    server_status,
    set_active_session,
)

_WS_IN_GOAL = re.compile(
    r"(?i)(?:"
    r"new\s+session(?:\s+path)?\s*:?\s*|"
    r"(?:change|switch)(?:\s+\w+){0,6}\s+workspace(?:\s+to)?\s*|"
    r"workspace(?:\s+path)?\s*(?:to\s*|:)\s*"
    r")(/[\w./~-]+|~[\w./~-]+|[\w][\w./~-]*)"
)
_ABS_PATH = re.compile(r"(/home/[\w./~-]+)")


def _extract_workspace_from_goal(goal: str) -> str:
    text = (goal or "").strip()
    m = _WS_IN_GOAL.search(text)
    if m:
        raw = m.group(1).strip()
        if raw.startswith("/") or raw.startswith("~"):
            return str(Path(raw).expanduser()).rstrip("/")
        from core.path_utils import resolve_user_path

        res = resolve_user_path(raw, must_exist=True, must_be_dir=True)
        if res.ok:
            return res.path.rstrip("/")
        if res.suggestions:
            return res.suggestions[0].rstrip("/")
    m = _ABS_PATH.search(text)
    if m and re.search(r"(?i)(workspace|new\s+session|switch|change)", text):
        return m.group(1).rstrip("/")
    return ""


def _clean_goal(goal: str, workspace_hint: str) -> str:
    if not workspace_hint:
        return (goal or "").strip()
    text = (goal or "").strip()
    cleaned = _WS_IN_GOAL.sub("", text).strip()
    cleaned = re.sub(
        r"(?i)(?:change|switch).*?workspace(?:\s+to)?\s*/[\w./~-]+\s*",
        "",
        cleaned,
    ).strip()
    cleaned = re.sub(r"(?i)\s*path:\s*/[\w./~-]+\s*", "", cleaned).strip()
    if not cleaned or cleaned.lower() in ("path", "workspace", "to"):
        return "hello"
    return cleaned


def _is_ephemeral_workspace(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if "/pytest-" in p or "pytest-of-" in p:
        return True
    if p.startswith("/tmp/") and "pytest" in p:
        return True
    return False


def resolve_workspace(raw: str = "", goal: str = "") -> Path:
    from core.opencode.opencode_server import load_state, set_active_workspace

    wp = _extract_workspace_from_goal(goal) or (raw or "").strip()
    if wp:
        path = Path(wp).expanduser()
        if not path.is_dir():
            raise ValueError(f"Workspace not found: {path}")
        resolved = path.resolve()
        set_active_workspace(resolved)
        return resolved

    active = (load_state().get("active_workspace") or "").strip()
    if active and not _is_ephemeral_workspace(active):
        path = Path(active).expanduser()
        if path.is_dir():
            return path.resolve()
    srv_ws = (server_status().get("server") or {}).get("workspace") or ""
    if srv_ws and not _is_ephemeral_workspace(srv_ws):
        path = Path(srv_ws).expanduser()
        if path.is_dir():
            return path.resolve()

    from memory.config_manager import get_base_dir

    lucas = get_base_dir()
    if lucas.is_dir():
        resolved = lucas.resolve()
        set_active_workspace(resolved)
        return resolved
    raise ValueError("workspace_path required.")


def _format_session_row(sess: dict, *, active_id: str = "") -> str:
    if not sess:
        return ""
    sid = str(sess.get("id") or "?")
    title = str(sess.get("title") or sess.get("slug") or "(untitled)")[:50]
    agent = str(sess.get("agent") or "?")
    directory = str(sess.get("directory") or "?")
    tag = " [ACTIVE]" if sid and sid == active_id else ""
    return f"- {sid}{tag}: {title} | agent={agent} | {directory}"


class OpenCodeAPI:
    def message(
        self,
        goal: str,
        *,
        workspace: str = "",
        action: str = "send",
        session_id: str = "",
        new_session: bool = False,
        parallel: bool = False,
    ) -> str:
        text = (goal or "").strip()
        if not text:
            return "goal= required."
        ws_hint = _extract_workspace_from_goal(text)
        try:
            ws = resolve_workspace(workspace, goal=text)
        except ValueError as exc:
            return str(exc)
        return oc_bg.launch(
            goal=_clean_goal(text, ws_hint),
            ws=ws,
            action=action,
            session_id=session_id,
            new_session=new_session,
            parallel=parallel,
        )

    def task(self, goal: str, *, workspace: str = "", **_) -> str:
        return self.message(goal, workspace=workspace, action="task")

    def send(self, goal: str, *, workspace: str = "", **_) -> str:
        return self.message(goal, workspace=workspace, action="send")

    def chat(
        self,
        goal: str,
        *,
        workspace: str = "",
        session_id: str = "",
        new_session: bool = False,
        parallel: bool = False,
        chat_timeout: float = 900.0,
    ) -> str:
        text = (goal or "").strip()
        if not text:
            return "goal= required."
        ws_hint = _extract_workspace_from_goal(text)
        try:
            ws = resolve_workspace(workspace, goal=text)
        except ValueError as exc:
            return str(exc)
        return oc_bg.launch_chat(
            goal=_clean_goal(text, ws_hint),
            ws=ws,
            action="chat",
            session_id=session_id,
            new_session=new_session,
            parallel=parallel,
            chat_timeout=chat_timeout,
        )

    def follow_up(
        self,
        message: str,
        *,
        workspace: str = "",
        session_id: str = "",
    ) -> str:
        text = (message or "").strip()
        if not text:
            return "follow_up= required."

        if not session_id:
            fg = oc_jobs.foreground_token()
            if fg:
                q = oc_bg.find_chat_by_token(fg)
                if q:
                    q.put(text)
                    return f"[follow_up] QUEUED\n\nSent to session {q.session_id}: {text[:200]}"
            return "[follow_up] ERROR\n\nNo active chat session. Start one with action=chat first."

        q = oc_bg.get_chat_queue(session_id)
        if not q:
            return f"[follow_up] ERROR\n\nNo active chat session for session {session_id}. Start one with action=chat first."
        q.put(text)
        return f"[follow_up] QUEUED\n\nSent to session {session_id}: {text[:200]}"

    def end_chat(self, session_id: str = "") -> str:
        if not session_id:
            fg = oc_jobs.foreground_token()
            if fg:
                q = oc_bg.find_chat_by_token(fg)
                if q:
                    q.signal_end()
                    return f"[end_chat] OK\n\nEnding chat session {q.session_id}."
            return "[end_chat] ERROR\n\nNo active chat session. Use session_id= to specify one."

        q = oc_bg.get_chat_queue(session_id)
        if not q:
            return f"[end_chat] ERROR\n\nNo active chat session for session {session_id}."
        q.signal_end()
        return f"[end_chat] OK\n\nEnding chat session {session_id}."

    def status(self) -> str:
        st = server_status()
        srv = st.get("server") or {}
        last = oc_flow.last_turn(st)
        active_ws = (st.get("active_workspace") or "").strip()
        sid = st.get("active_session_id") or oc_bg.pending_job().get("session_id") or ""
        lines = [
            f"server: {'running' if srv.get('running') else 'stopped'}",
            f"workspace: {srv.get('workspace') or '(none)'}",
            f"active_workspace: {active_ws or '(default: Lucas repo)'}",
            f"session: {sid or '(none)'}",
            f"agent: {DEFAULT_AGENT}",
            f"model: {st.get('default_model') or DEFAULT_MODEL}",
        ]
        jobs = oc_jobs.list_jobs(running_only=True)
        if jobs:
            lines.append(f"running_jobs: {len(jobs)}")
            for job in jobs[:8]:
                tok = str(job.get("token") or "")[-10:]
                lines.append(
                    f"  · {tok}: {str(job.get('goal') or '')[:50]} "
                    f"({job.get('phase')}) ws={Path(str(job.get('workspace') or '')).name}"
                )
        servers = list_servers()
        if len(servers) > 1:
            lines.append(f"opencode_servers: {len(servers)}")
            for srv in servers[:6]:
                lines.append(
                    f"  · {Path(str(srv.get('workspace') or '')).name}: "
                    f"port={srv.get('port')} running={srv.get('running')}"
                )
        job = oc_bg.pending_job()
        if job.get("phase") and len(jobs) <= 1:
            lines.append(f"job: {job.get('phase')} — {str(job.get('goal') or '')[:80]}")
        if last.get("reply"):
            lines.append(f"last: {last['reply'][:200]}")
        extra = oc_bg.format_status_extra()
        if extra:
            lines.append(extra)
        if srv.get("running"):
            try:
                client = get_client()
                lines.append(f"version: {client.health().get('version', '?')}")
                agents = client.list_agents()
                names = [
                    str(a.get("name") or "?")
                    for a in agents
                    if isinstance(a, dict) and a.get("name")
                ][:12]
                if names:
                    lines.append(f"agents: {', '.join(names)}")
                if sid:
                    children = client.session_children(sid) or []
                    if children:
                        child_titles = [
                            str(c.get("title") or c.get("id") or "?")[:40]
                            for c in children
                            if isinstance(c, dict)
                        ][:8]
                        lines.append(
                            f"sub-agents ({len(children)}): {', '.join(child_titles)}"
                        )
                    status_map = client.session_status() or {}
                    entry = status_map.get(sid) if isinstance(status_map, dict) else None
                    if isinstance(entry, dict) and entry.get("status"):
                        lines.append(f"session_status: {entry.get('status')}")
            except OpenCodeError:
                pass
        try:
            from core.opencode import opencode_trace as oc_trace

            digest = oc_trace.format_digest()
            if digest:
                lines.append(f"trace:\n{digest[:600]}")
        except Exception:
            pass
        if jobs:
            lines.append(
                "cancel: job_cancel_all (all) | job_cancel job_token=<short id> (one) | cancel (foreground)"
            )
        return "[status] OK\n\n" + "\n".join(lines)

    def trace(self) -> str:
        from core.opencode import opencode_trace as oc_trace

        digest = oc_trace.format_digest()
        if not digest:
            return "[trace] OK\n\n(no active OpenCode job — use status or session_list)"
        return f"[trace] OK\n\n{digest}"

    def session_list(self, *, workspace: str = "", limit: int = 15) -> str:
        ws = resolve_workspace(workspace) if workspace else None
        client = ensure_server(ws) if ws else get_client()
        active = (load_state().get("active_session_id") or "").strip()
        sessions = client.list_sessions() or []
        if not isinstance(sessions, list):
            sessions = []
        rows = [
            _format_session_row(sess, active_id=active)
            for sess in sessions[:limit]
            if isinstance(sess, dict)
        ]
        header = f"active_session: {active or '(none)'}"
        body = "\n".join(rows) if rows else "(no sessions)"
        return f"[session_list] OK\n\n{header}\n\n{body}"

    def session_use(self, session_id: str, *, workspace: str = "") -> str:
        sid = (session_id or "").strip()
        if not sid:
            return "session_id= required."
        if workspace:
            resolve_workspace(workspace)
        client = get_client()
        sess = client.get_session(sid)
        if not sess:
            return f"[session_use] ERROR\n\nSession not found: {sid}"
        set_active_session(sid)
        title = str(sess.get("title") or sess.get("slug") or "(untitled)")
        return f"[session_use] OK\n\nactive session: {sid}\ntitle: {title}"

    def session_new(self, *, title: str = "", workspace: str = "") -> str:
        ws = resolve_workspace(workspace)
        client = ensure_server(ws)
        sess = client.create_session(title=(title or "New session")[:80])
        sid = str(sess.get("id") or "")
        if not sid:
            return "[session_new] ERROR\n\nFailed to create session."
        set_active_session(sid)
        return f"[session_new] OK\n\nsession: {sid}\nworkspace: {ws}"

    def session_delete(self, session_id: str) -> str:
        sid = (session_id or "").strip()
        if not sid:
            return "session_id= required."
        client = get_client()
        client.delete_session(sid)
        st = load_state()
        if st.get("active_session_id") == sid:
            set_active_session("")
            oc_bg.clear_pending()
        return f"[session_delete] OK\n\nDeleted {sid}."

    def jobs_list(self) -> str:
        jobs = oc_jobs.list_jobs()
        running = [j for j in jobs if j.get("running")]
        if not jobs:
            return "[jobs_list] OK\n\n(no jobs)"
        lines = []
        for job in jobs:
            tok = str(job.get("token") or "")
            short = tok[-10:] if tok else "?"
            phase = str(job.get("phase") or "?")
            run = "RUN" if job.get("running") else "done"
            lines.append(
                f"- {short} [{run}/{phase}] {str(job.get('goal') or '')[:60]} "
                f"| ws={Path(str(job.get('workspace') or '')).name}"
            )
        footer = (
            f"\n\nrunning: {len(running)} | "
            "cancel all: job_cancel_all | cancel one: job_cancel job_token=<short id above>"
        )
        return "[jobs_list] OK\n\n" + "\n".join(lines) + footer

    def job_cancel(self, job_token: str = "") -> str:
        return oc_bg.cancel_job(job_token)

    def job_cancel_all(self) -> str:
        return oc_bg.cancel_all_jobs()

    def spawn(self, goal: str, *, workspace: str = "", **kwargs) -> str:
        return self.message(goal, workspace=workspace, action="send", parallel=True, **kwargs)

    def cancel(self, job_token: str = "") -> str:
        if job_token:
            return self.job_cancel(job_token)
        return oc_bg.cancel_job()

    def window_list(self) -> str:
        mgr = oc_bg.get_window_manager()
        if mgr is None:
            return "[window_list] OK\n\nNo OpenCode windows open."
        return "[window_list] OK\n\n" + mgr.list_windows()

    def open_window(self, goal: str = "") -> str:
        """Create and show the OpenCode tracker window."""
        mgr = oc_bg.get_window_manager()
        if mgr is None:
            return "[open_window] ERROR\n\nNo window manager available — Lucas UI not running?"
        if not hasattr(mgr, "_ensure_parent"):
            return "[open_window] ERROR\n\nWindow manager does not support _ensure_parent."
        try:
            # Create a dummy job payload so the manager creates the parent window
            import time

            dummy = {
                "token": f"manual_{time.time_ns()}",
                "goal": goal or "OpenCode Tracker",
                "phase": "idle",
                "workspace": "",
                "parallel": False,
            }
            mgr.on_job(dummy)
            return "[open_window] OK\n\nOpenCode tracker window opened."
        except Exception as exc:
            return f"[open_window] ERROR\n\n{exc}"

    def close_window(self, job_token: str = "", goal: str = "") -> str:
        mgr = oc_bg.get_window_manager()
        if mgr is None:
            return "[close_window] OK\n\nNo OpenCode windows open."
        result = mgr.close_window(token=job_token, goal=goal)
        return f"[close_window] OK\n\n{result}"

    def commands_list(self, *, workspace: str = "") -> str:
        ws = resolve_workspace(workspace)
        cmds = ensure_server(ws).list_commands()
        lines = [
            f"/{c.get('name')} — {(c.get('description') or '')[:100]}"
            for c in cmds
            if isinstance(c, dict) and c.get("name")
        ]
        return "[commands_list] OK\n\n" + ("\n".join(lines) if lines else "(none)")

    def command(self, command: str, *, arguments: str = "", workspace: str = "") -> str:
        raw = (command or "").strip().lstrip("/")
        args = (arguments or "").strip()
        if not raw:
            return "command= required."
        if not args and " " in raw:
            raw, args = raw.split(None, 1)
        if raw in ("find", "grep"):
            return self.find(args or ".", workspace=workspace)
        if raw in ("read", "read_file", "file", "cat"):
            return self.read_file(args, workspace=workspace)
        ws = resolve_workspace(workspace)
        registered = {
            str(c.get("name") or "")
            for c in ensure_server(ws).list_commands()
            if isinstance(c, dict) and c.get("name")
        }
        if raw not in registered:
            names = ", ".join(f"/{n}" for n in sorted(registered)[:12]) or "(none)"
            return f"[command] ERROR\n\n/{raw} not registered. Known: {names}"
        return oc_bg.launch_command(
            label=f"/{raw}" + (f" {args}" if args else ""),
            cmd=raw,
            arguments=args,
            ws=ws,
        )

    def find(self, pattern: str, *, workspace: str = "") -> str:
        pat = (pattern or "").strip() or "."
        ws = resolve_workspace(workspace)
        client = ensure_server(ws)
        if pat in (".", "*"):
            paths = client.list_workspace_files(limit=80)
            if not paths:
                try:
                    paths = [p.name for p in sorted(ws.iterdir()) if not p.name.startswith(".")][:80]
                except OSError:
                    paths = []
            return "[find] OK\n\n" + ("\n".join(paths) if paths else "(empty)")
        hits = client.find_text(pat)
        lines = []
        for h in hits[:40]:
            if not isinstance(h, dict):
                continue
            path = h.get("path") or h.get("file") or "?"
            line = h.get("line_number") or h.get("line") or ""
            text = (h.get("text") or h.get("content") or "")[:120]
            lines.append(f"{path}:{line}: {text}".rstrip(": "))
        return "[find] OK\n\n" + ("\n".join(lines) if lines else "(no matches)")

    def read_file(self, path: str, *, workspace: str = "") -> str:
        rel = (path or "").strip()
        if not rel:
            return "path= required."
        payload = ensure_server(resolve_workspace(workspace)).read_file(rel)
        content = ""
        if isinstance(payload, dict):
            content = str(payload.get("content") or payload.get("text") or "")
        return f"[read_file] OK\n\n{content[:12000]}"

    # --- question relay ---------------------------------------------------

    def questions_list(self) -> str:
        """List pending OpenCode questions for Lucas to relay aloud."""
        try:
            client = get_client()
            pending = client.list_questions() or []
        except OpenCodeError as exc:
            return f"[questions_list] ERROR\n\n{str(exc)[:300]}"
        rows = []
        for req in pending:
            if not isinstance(req, dict):
                continue
            req_id = str(req.get("id") or req.get("requestID") or "?")
            question = str(
                req.get("question") or req.get("text") or req.get("message") or ""
            ).strip()
            sid = str(req.get("sessionID") or req.get("session_id") or "")
            rows.append(f"- {req_id}: {question} (session {sid})" if sid else f"- {req_id}: {question}")
        if not rows:
            return "[questions_list] OK\n\n(no pending questions)"
        return "[questions_list] OK\n\n" + "\n".join(rows)

    def question_ask(self, request_id: str = "", answer: str = "") -> str:
        """Relay a pending OpenCode question to the user (or submit an answer).

        With *answer* set, replies via ``reply_question``. Without it and with
        no request_id, returns the first pending question so the model speaks it.
        """
        request_id = (request_id or "").strip()
        answer = (answer or "").strip()
        if answer:
            if not request_id:
                return "[question_ask] ERROR\n\nrequest_id= required to submit an answer."
            try:
                get_client().reply_question(request_id, answers=[answer])
                return f"[question_ask] OK\n\nReplied to {request_id}: {answer[:200]}"
            except OpenCodeError as exc:
                return f"[question_ask] ERROR\n\n{str(exc)[:300]}"
        try:
            client = get_client()
            pending = client.list_questions() or []
        except OpenCodeError as exc:
            return f"[question_ask] ERROR\n\n{str(exc)[:300]}"
        for req in pending:
            if not isinstance(req, dict):
                continue
            req_id = str(req.get("id") or req.get("requestID") or "")
            if request_id and req_id != request_id:
                continue
            question = str(
                req.get("question") or req.get("text") or req.get("message") or ""
            ).strip()
            return (
                f"[question_ask] RELAY\n\nrequest_id: {req_id}\n"
                f"OpenCode asks: {question}"
            )
        return "[question_ask] OK\n\n(no pending questions)"

    def answer_question(self, request_id: str, answer: str) -> str:
        """Submit the user's spoken answer to a pending OpenCode question."""
        request_id = (request_id or "").strip()
        answer = (answer or "").strip()
        if not request_id or not answer:
            return "[answer_question] ERROR\n\nrequest_id= and answer= required."
        try:
            get_client().reply_question(request_id, answers=[answer])
            return f"[answer_question] OK\n\nReplied to {request_id}: {answer[:200]}"
        except OpenCodeError as exc:
            return f"[answer_question] ERROR\n\n{str(exc)[:300]}"

    def question_reject(self, request_id: str) -> str:
        """Tell OpenCode "never mind" for a pending question."""
        request_id = (request_id or "").strip()
        if not request_id:
            return "[question_reject] ERROR\n\nrequest_id= required."
        try:
            get_client().reject_question(request_id)
            return f"[question_reject] OK\n\nRejected question {request_id}."
        except OpenCodeError as exc:
            return f"[question_reject] ERROR\n\n{str(exc)[:300]}"

    # -- permission gate (approval) -----------------------------------------

    def permissions_list(self) -> str:
        """List pending OpenCode permission requests awaiting user decision."""
        rows: list[str] = []
        try:
            client = get_client()
            pending = client.list_permissions() or []
        except OpenCodeError as exc:
            return f"[permissions_list] ERROR\n\n{str(exc)[:300]}"
        for req in pending:
            if not isinstance(req, dict):
                continue
            req_id = str(req.get("id") or "?")
            desc = str(
                req.get("description")
                or req.get("message")
                or req.get("reason")
                or req.get("text")
                or ""
            ).strip()
            sid = str(req.get("sessionID") or req.get("session_id") or "")
            row = f"- {req_id}: {desc}"
            if sid:
                row += f" (session {sid})"
            rows.append(row)
        if not rows:
            return "[permissions_list] OK\n\n(no pending permissions)"
        return "[permissions_list] OK\n\n" + "\n".join(rows)

    @staticmethod
    def _resolve_session_for_request(request_id: str, session_id: str = "") -> str:
        """Best-effort session id for a session-scoped permission request."""
        sid = (session_id or "").strip()
        if sid:
            return sid
        try:
            from core.opencode.opencode_server import pending_permissions

            for req in pending_permissions():
                if isinstance(req, dict) and str(req.get("id") or "") == request_id:
                    candidate = str(req.get("sessionID") or req.get("session_id") or "")
                    if candidate:
                        return candidate
        except Exception:
            pass
        return (load_state().get("active_session_id") or "").strip()

    def permission_approve(
        self,
        request_id: str = "",
        *,
        session_id: str = "",
        permission: str = "once",
    ) -> str:
        """Approve a pending permission request (global or session-scoped)."""
        request_id = (request_id or "").strip()
        if not request_id:
            request_id = self._first_pending_request_id()
            if not request_id:
                return "[approve] ERROR\n\nNo pending permission requests. Use permissions_list."
        try:
            client = get_client()
            if request_id.startswith("per") and permission != "session":
                client.reply_permission(request_id, reply=permission)
            else:
                sid = self._resolve_session_for_request(request_id, session_id)
                client.reply_session_permission(sid, request_id, response="allow")
            return f"[approve] OK\n\nApproved {request_id}."
        except OpenCodeError as exc:
            return f"[approve] ERROR\n\n{str(exc)[:300]}"

    def permission_deny(self, request_id: str = "", *, session_id: str = "") -> str:
        """Deny a pending permission request (global or session-scoped)."""
        request_id = (request_id or "").strip()
        if not request_id:
            request_id = self._first_pending_request_id()
            if not request_id:
                return "[deny] ERROR\n\nNo pending permission requests. Use permissions_list."
        try:
            client = get_client()
            if request_id.startswith("per") and not session_id:
                client.reply_permission(request_id, reply="reject")
            else:
                sid = self._resolve_session_for_request(request_id, session_id)
                client.reply_session_permission(sid, request_id, response="reject")
            return f"[deny] OK\n\nDenied {request_id}."
        except OpenCodeError as exc:
            return f"[deny] ERROR\n\n{str(exc)[:300]}"

    def _first_pending_request_id(self) -> str:
        try:
            for req in get_client().list_permissions() or []:
                if isinstance(req, dict):
                    rid = str(req.get("id") or "")
                    if rid:
                        return rid
        except OpenCodeError:
            pass
        return ""

    # -- session diff / revert ----------------------------------------------

    def session_diff(self, session_id: str = "", *, message_id: str = "") -> str:
        """Show file changes produced by a session/message via ``session_diff``."""
        sid = (session_id or "").strip() or get_active_session()
        if not sid:
            return "[diff] ERROR\n\nNo active session. Use session_list first or pass session_id=."
        try:
            diffs = get_client().session_diff(sid, message_id=message_id) or []
        except OpenCodeError as exc:
            return f"[diff] ERROR\n\n{str(exc)[:300]}"
        lines = [f"diff for session {sid}: {len(diffs)} file change(s)"]
        for d in diffs[:20]:
            if not isinstance(d, dict):
                continue
            path = d.get("path") or d.get("file") or "?"
            status = d.get("status") or d.get("type") or ""
            lines.append(f"- {path} ({status})")
        return "[diff] OK\n\n" + "\n".join(lines)

    def session_revert(self, session_id: str = "", *, message_id: str = "") -> str:
        """Revert a session (or a specific message) to undo its changes."""
        sid = (session_id or "").strip() or get_active_session()
        if not sid:
            return "[revert] ERROR\n\nNo active session. Use session_list first."
        try:
            get_client().session_revert(sid, message_id=message_id)
        except OpenCodeError as exc:
            return f"[revert] ERROR\n\n{str(exc)[:300]}"
        if message_id:
            return f"[revert] OK\n\nReverted session {sid} to before message {message_id}."
        return f"[revert] OK\n\nReverted session {sid} to its starting point."

    # -- workspace control ----------------------------------------------------

    def workspace_list(self) -> str:
        """List the OpenCode server pool and the active workspace."""
        rows: list[str] = []
        for srv in list_servers():
            ws = str(srv.get("workspace") or "")
            running = bool(srv.get("running"))
            port = srv.get("port") or "?"
            rows.append(f"- {ws}: running={running} port={port}")
        active = (load_state().get("active_workspace") or "").strip()
        header = f"active_workspace: {active or '(default: Lucas repo)'}"
        body = "\n".join(rows) if rows else "(no servers)"
        return "[list_workspace] OK\n\n" + header + "\n\n" + body

    def workspace_set(self, path: str) -> str:
        """Activate *path* as the OpenCode workspace (starts it in the pool)."""
        raw = (path or "").strip()
        if not raw:
            return "[set_workspace] ERROR\n\nworkspace_path= required."
        try:
            ws = Path(raw).expanduser()
            if not ws.is_dir():
                return f"[set_workspace] ERROR\n\nWorkspace not found: {ws}"
            ensure_server(ws)
            resolved = str(ws.resolve())
            return f"[set_workspace] OK\n\nactive workspace: {resolved}"
        except Exception as exc:
            return f"[set_workspace] ERROR\n\n{str(exc)[:300]}"

    def workspace_switch(self, path: str) -> str:
        """Switch the active OpenCode workspace to *path*."""
        raw = (path or "").strip()
        if not raw:
            return "[switch_workspace] ERROR\n\nworkspace_path= required."
        try:
            ws = Path(raw).expanduser()
            if not ws.is_dir():
                return f"[switch_workspace] ERROR\n\nWorkspace not found: {ws}"
            ensure_server(ws)
            resolved = str(ws.resolve())
            return f"[switch_workspace] OK\n\nSwitched active workspace to {resolved}."
        except Exception as exc:
            return f"[switch_workspace] ERROR\n\n{str(exc)[:300]}"


_api: OpenCodeAPI | None = None


def get_opencode() -> OpenCodeAPI:
    global _api
    if _api is None:
        _api = OpenCodeAPI()
    return _api
