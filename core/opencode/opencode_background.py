"""Background OpenCode — goal in, STARTED out, COMPLETE when done. Supports parallel jobs."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.opencode import opencode_flow as oc_flow
from core.opencode import opencode_jobs as oc_jobs
from core.logger import get_logger
from core.opencode.opencode_client import extract_message_text, format_voice_reply
from core.opencode.opencode_defaults import DEFAULT_AGENT, DEFAULT_MODEL, MAX_PARALLEL_JOBS
from core.opencode.opencode_server import (
    PermissionAutoApprover,
    _server_alive,
    _servers_map,
    ensure_server,
    get_client,
    load_state,
    save_state,
    set_active_session,
    set_active_workspace,
)

from core.opencode import opencode_trace as oc_trace
from core.opencode.opencode_client import format_terminal_reply
from core.opencode.opencode_events import EventSubscriber, wait_session_idle
from core.opencode.opencode_relay import ReplyRelay
from core.opencode.opencode_chat import FollowUpQueue

logger = get_logger(__name__)


def classify_opencode_error(exc: Exception, job_state: dict | None = None) -> dict:
    """Categorize OpenCode errors for user-friendly reporting."""
    err_str = str(exc).lower()

    if "connectionrefused" in err_str or "connection refused" in err_str or "no route to host" in err_str:
        return {"category": "server_down", "message": "OpenCode server couldn't be reached"}
    if "timed out" in err_str or "timeout" in err_str:
        return {"category": "timeout", "message": "OpenCode timed out"}
    if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
        return {"category": "quota", "message": "OpenCode hit an API rate limit"}
    if "permission" in err_str and ("denied" in err_str or "forbidden" in err_str):
        return {"category": "permission", "message": "OpenCode file permission denied"}
    if "not found" in err_str and ("binary" in err_str or "command" in err_str or "opencode" in err_str):
        return {"category": "binary_missing", "message": "OpenCode binary not found"}

    return {"category": "unknown", "message": str(exc)}

Meta = dict[str, Any]
ReplyHandler = Callable[[str, bool, Meta], None]
CompletionHandler = Callable[[str, Meta], None]

_completion_handler: CompletionHandler | None = None
_reply_handler: ReplyHandler | None = None
_reply_reset_handler: Callable[[], None] | None = None
_job_started_handler: Callable[[dict], None] | None = None
_progress_handler: Callable[[dict], None] | None = None
_stream_handler: ReplyHandler | None = None
_window_manager: object | None = None
_job_lock = threading.Lock()


def set_completion_handler(fn: CompletionHandler | None) -> None:
    global _completion_handler
    _completion_handler = fn


def set_reply_handler(fn: ReplyHandler | None) -> None:
    global _reply_handler
    _reply_handler = fn


def set_reply_reset_handler(fn: Callable[[], None] | None) -> None:
    global _reply_reset_handler
    _reply_reset_handler = fn


def _reset_reply_state() -> None:
    if _reply_reset_handler:
        try:
            _reply_reset_handler()
        except Exception as exc:
            logger.debug("[opencode_background] reply_reset: %s", exc)


def set_job_started_handler(fn: Callable[[dict], None] | None) -> None:
    global _job_started_handler
    _job_started_handler = fn


def set_progress_handler(fn: Callable[[dict], None] | None) -> None:
    global _progress_handler
    _progress_handler = fn


def set_stream_handler(fn: ReplyHandler | None) -> None:
    global _stream_handler
    _stream_handler = fn


_chat_sessions: dict[str, FollowUpQueue] = {}
_chat_sessions_lock = threading.Lock()


def _register_chat(session_id: str, queue: FollowUpQueue) -> None:
    with _chat_sessions_lock:
        _chat_sessions[session_id] = queue


def _unregister_chat(session_id: str) -> None:
    with _chat_sessions_lock:
        _chat_sessions.pop(session_id, None)


def get_chat_queue(session_id: str) -> FollowUpQueue | None:
    with _chat_sessions_lock:
        return _chat_sessions.get(session_id)


def find_chat_by_token(token: str) -> FollowUpQueue | None:
    """Find the chat queue for a given job token."""
    job = oc_jobs.get(token)
    if not job:
        return None
    sid = str(job.get("session_id") or "")
    if not sid:
        return None
    return get_chat_queue(sid)


def _latch_pending_questions(client, chat_queue: FollowUpQueue, sid: str, job: dict) -> None:
    """Surface OpenCode questions for *sid* to the user and latch them.

    Polls ``GET /question``; when a pending question targets this session, latch
    it on the chat queue so the next user utterance is routed via
    ``reply_question``, and notify Lucas to relay the question aloud.
    """
    try:
        pending = client.list_questions() or []
    except Exception as exc:
        logger.debug("[opencode_background] list_questions: %s", exc)
        return
    for req in pending:
        if not isinstance(req, dict):
            continue
        req_id = str(req.get("id") or req.get("requestID") or "")
        if not req_id:
            continue
        req_sid = str(
            req.get("sessionID") or req.get("session_id") or ""
        )
        if req_sid and req_sid != sid:
            continue
        if chat_queue.has_question():
            continue
        question = str(
            req.get("question") or req.get("text") or req.get("message") or ""
        ).strip()
        chat_queue.latch_question(req_id, question)
        logger.info("[opencode_background] latched question %s for %s", req_id, sid)
        try:
            _emit_progress(
                {
                    **job,
                    "phase": "question",
                    "question": question,
                    "request_id": req_id,
                }
            )
        except Exception:
            pass
        _notify(
            f"[question] OPENCODE ASKS\n\n{question}\n\n"
            "Relay this question to the user now and wait for their spoken answer.",
            token=str(job.get("token") or ""),
            meta={**job, "phase": "question", "request_id": req_id},
        )
        break


def set_window_manager(mgr: object | None) -> None:
    global _window_manager
    _window_manager = mgr


def get_window_manager() -> object | None:
    return _window_manager


def _emit_job_started(payload: dict) -> None:
    try:
        oc_trace.ingest(dict(payload))
    except Exception as exc:
        logger.debug("[opencode_background] trace job: %s", exc)
    if _job_started_handler:
        try:
            _job_started_handler(dict(payload))
        except Exception as exc:
            logger.debug("[opencode_background] job_started: %s", exc)


def _emit_progress(payload: dict) -> None:
    token = str(payload.get("token") or "")
    if token:
        reg = oc_jobs.get(token)
        if reg.get("parallel") and not payload.get("parallel"):
            payload = {**payload, "parallel": True}
        if reg.get("new_session") and not payload.get("new_session"):
            payload = {**payload, "new_session": True}
        oc_jobs.update(
            token,
            **{k: v for k, v in payload.items() if k not in ("client", "token")},
        )
    try:
        trace_payload = {k: v for k, v in payload.items() if k != "client"}
        oc_trace.ingest(trace_payload)
    except Exception as exc:
        logger.debug("[opencode_background] trace progress: %s", exc)
    if _progress_handler:
        try:
            clean = {k: v for k, v in payload.items() if k != "client"}
            _progress_handler(clean)
        except Exception as exc:
            logger.debug("[opencode_background] progress: %s", exc)


_speak_handler: Callable[[str], None] | None = None


def set_speak_handler(fn: Callable[[str], None] | None) -> None:
    global _speak_handler
    _speak_handler = fn


def pending_job() -> dict:
    return oc_jobs.pending_job()


def clear_pending() -> None:
    fg = oc_jobs.foreground_token()
    if fg:
        oc_jobs.remove(fg)


def is_running() -> bool:
    return oc_jobs.is_running()


def _ws_key(ws: Path) -> str:
    return str(ws.expanduser().resolve())


def _session_matches_workspace(sess: dict, ws: Path) -> bool:
    sess_dir = str(sess.get("directory") or "").strip()
    if not sess_dir:
        return True
    try:
        return Path(sess_dir).resolve() == ws.resolve()
    except OSError:
        return False


def _client_for_job(job: dict) -> Any:
    ws = str(job.get("workspace") or "").strip()
    if ws:
        return ensure_server(Path(ws))
    return get_client()


def _resolve_session_id(
    client,
    ws: Path,
    *,
    session_id: str = "",
    new_session: bool = False,
    goal: str = "",
) -> str:
    sid = (session_id or "").strip()
    if new_session:
        sid = ""
    if sid:
        try:
            sess = client.get_session(sid)
            if not isinstance(sess, dict) or not _session_matches_workspace(sess, ws):
                logger.warning(
                    "[opencode_background] session %s not valid for %s — creating new",
                    sid,
                    ws,
                )
                sid = ""
        except Exception as exc:
            logger.debug("[opencode_background] session lookup %s: %s", sid, exc)
            sid = ""
    if not sid:
        sess = client.create_session(title=(goal or "Lucas task")[:80])
        sid = str(sess.get("id") or "")
        if not sid:
            raise RuntimeError("Failed to create OpenCode session.")
    return sid


def _fetch_last_message(client, sid: str, relay: Any, *, goal: str = "") -> dict:
    msgs = client.list_messages(sid, limit=20, missing_ok=True)
    if msgs:
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "assistant":
                return m
    if relay:
        text = relay.final_text()
        if text:
            # Detect goal-echo: if the relay text is identical to the goal
            # or only trivially longer, it's an echo, not a real assistant reply.
            goal_clean = goal.strip()
            if goal_clean and text[: len(goal_clean)] == goal_clean and len(text) <= len(goal_clean) + 5:
                logger.warning(
                    "[opencode_background] relay text matches goal for %s — "
                    "likely model echo, not a real reply",
                    sid,
                )
                return {}
            logger.info(
                "[opencode_background] list_messages empty for %s — using streamed reply",
                sid,
            )
            return {
                "info": {"sessionID": sid, "finish": "stop"},
                "parts": [{"type": "text", "text": text}],
            }
    return {}


def _abort_job(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    job = oc_jobs.get(token)
    sid = str(job.get("session_id") or load_state().get("active_session_id") or "")
    if sid:
        try:
            _client_for_job(job).abort_session(sid)
        except Exception as exc:
            logger.debug("[opencode_background] abort %s: %s", sid, exc)
    oc_jobs.remove(token)
    oc_jobs.mark_inactive(token)
    try:
        oc_trace.remove(token)
    except Exception:
        pass


def _abort_foreground() -> None:
    fg = oc_jobs.foreground_token()
    if fg:
        _abort_job(fg)
    else:
        job = pending_job()
        if job.get("session_id") or job.get("token"):
            _abort_job(str(job.get("token") or ""))


def _job_meta(job: dict) -> Meta:
    return {
        "token": str(job.get("token") or ""),
        "goal": str(job.get("goal") or "")[:200],
        "session_id": str(job.get("session_id") or ""),
        "workspace": str(job.get("workspace") or ""),
        "action": str(job.get("action") or ""),
    }


def _notify(block: str, *, token: str = "", meta: Meta | None = None) -> None:
    if token and not oc_jobs.is_token_active(token):
        return
    try:
        print(format_terminal_reply(block), flush=True)
    except Exception as exc:
        logger.debug("[opencode_background] terminal: %s", exc)
    if _completion_handler:
        try:
            _completion_handler(block, meta or {})
        except Exception as exc:
            logger.warning("[opencode_background] completion: %s", exc)


def _worker(
    *,
    goal: str,
    ws: Path,
    action: str,
    token: str,
    session_id: str = "",
    new_session: bool = False,
    parallel: bool = False,
) -> None:
    sid = ""
    subscriber = None
    relay = None
    client = None
    job: dict[str, Any] = {}
    try:
        client = ensure_server(ws)
        model = (load_state().get("default_model") or DEFAULT_MODEL).strip()
        if not oc_jobs.is_token_active(token):
            return

        sid = _resolve_session_id(
            client,
            ws,
            session_id=session_id,
            new_session=new_session,
            goal=goal,
        )
        set_active_session(sid)
        job = {
            "token": token,
            "action": action,
            "goal": goal[:500],
            "session_id": sid,
            "workspace": str(ws),
            "parallel": parallel,
            "new_session": new_session,
            "started_at": time.time(),
            "phase": "running",
        }
        oc_jobs.update(token, **{k: v for k, v in job.items() if k != "token"})
        _emit_progress({**job, "client": client})

        meta = _job_meta(job)

        def _on_reply(reply: str, final: bool, _meta: Meta) -> None:
            if _reply_handler:
                _reply_handler(reply, final, _meta)
            if not final and _stream_handler:
                _stream_handler(reply, final, _meta)

        relay = ReplyRelay(token, _on_reply, meta=meta)

        def _on_event(event_type: str, props: dict) -> None:
            relay.on_event(event_type, props)
            _emit_progress({**job, "event_type": event_type, "properties": props})

        subscriber = EventSubscriber(client, session_id=sid, on_event=_on_event)
        subscriber.start()

        approver = PermissionAutoApprover(
            client,
            mode="always" if load_state().get("auto_approve_permissions") else "gate",
        )
        approver.start()
        try:
            client.prompt_async(
                sid,
                text=goal,
                model=model,
                agent=DEFAULT_AGENT,
            )
            # Wait indefinitely for session.idle via SSE.
            # If the SSE stream drops before idle arrives, fall back to
            # HTTP polling with a generous timeout and cancellation support.
            idle = subscriber.wait_until_idle(timeout=120)
            if not idle:
                if not oc_jobs.is_token_active(token):
                    return
                logger.info(
                    "[opencode_background] SSE ended without idle for %s — polling HTTP",
                    sid,
                )
                wait_session_idle(
                    client,
                    sid,
                    timeout=7200,
                    token=token,
                )
        finally:
            approver.stop()
            relay.close()
            subscriber.stop()

        if not oc_jobs.is_token_active(token):
            return

        try:
            children = client.session_children(sid) or []
            if children:
                oc_trace.note_subagents(token, children)
        except Exception:
            pass

        result = _fetch_last_message(client, sid, relay, goal=goal)
        if not result:
            raise RuntimeError(
                "OpenCode produced no assistant reply. "
                "Check model/provider config (opencode_control status) "
                "and serve log (memory/opencode_serve.log)."
            )
        reply = extract_message_text(result if isinstance(result, dict) else {})
        voice = format_voice_reply(result if isinstance(result, dict) else {}, session_id=sid)
        oc_flow.record_turn(
            load_state,
            save_state,
            action=action,
            goal=goal,
            reply=reply,
            session_id=sid,
        )
        block = f"[{action}] COMPLETE job_token={token}\n\n{voice}"
        _notify(block, token=token, meta={**meta, "phase": "complete"})
        _emit_progress({**job, "phase": "complete", "error": ""})
        oc_jobs.finish(token, phase="complete")
        oc_jobs.mark_inactive(token)
        try:
            oc_trace.remove(token)
        except Exception:
            pass
    except Exception as exc:
        logger.exception("[opencode_background] %s: %s", action, exc)
        if relay:
            relay.close()
        if subscriber:
            subscriber.stop()
        if oc_jobs.is_token_active(token):
            meta = _job_meta(job or {"token": token, "goal": goal, "session_id": sid, "workspace": str(ws), "action": action})
            err = classify_opencode_error(exc, job or None)
            _notify(f"[{action}] ERROR job_token={token} ({err['category']})\n\n{err['message']}", token=token, meta={**meta, "phase": "error"})
            _emit_progress({**meta, "phase": "error", "error": str(exc)})
            oc_jobs.finish(token, phase="error", error=str(exc))
            oc_jobs.mark_inactive(token)
    if sid:
        set_active_session(sid)


def _chat_worker(
    *,
    goal: str,
    ws: Path,
    action: str,
    token: str,
    session_id: str = "",
    new_session: bool = False,
    parallel: bool = False,
    chat_timeout: float = 900.0,
) -> None:
    """Multi-turn chat worker — sends goal, then loops on FollowUpQueue for follow-ups."""
    sid = ""
    subscriber = None
    relay = None
    client = None
    job: dict[str, Any] = {}
    chat_queue: FollowUpQueue | None = None
    try:
        client = ensure_server(ws)
        model = (load_state().get("default_model") or DEFAULT_MODEL).strip()
        if not oc_jobs.is_token_active(token):
            return

        sid = _resolve_session_id(
            client,
            ws,
            session_id=session_id,
            new_session=new_session,
            goal=goal,
        )
        set_active_session(sid)
        job = {
            "token": token,
            "action": action,
            "goal": goal[:500],
            "session_id": sid,
            "workspace": str(ws),
            "parallel": parallel,
            "new_session": new_session,
            "mode": "chat",
            "chat_timeout": chat_timeout,
            "started_at": time.time(),
            "phase": "running",
        }
        oc_jobs.update(token, **{k: v for k, v in job.items() if k != "token"})
        _emit_progress({**job, "client": client})

        meta = _job_meta(job)

        def _on_reply(reply: str, final: bool, _meta: Meta) -> None:
            if _reply_handler:
                _reply_handler(reply, final, _meta)
            if not final and _stream_handler:
                _stream_handler(reply, final, _meta)

        relay = ReplyRelay(token, _on_reply, meta=meta)

        def _on_event(event_type: str, props: dict) -> None:
            relay.on_event(event_type, props)
            _emit_progress({**job, "event_type": event_type, "properties": props})

        subscriber = EventSubscriber(client, session_id=sid, on_event=_on_event)
        subscriber.start()

        approver = PermissionAutoApprover(
            client,
            mode="always" if load_state().get("auto_approve_permissions") else "gate",
        )
        approver.start()

        # ---- Initial prompt ----
        try:
            client.prompt_async(sid, text=goal, model=model, agent=DEFAULT_AGENT)
            idle = subscriber.wait_until_idle(timeout=120)
            if not idle:
                if not oc_jobs.is_token_active(token):
                    return
                logger.info("[opencode_background] chat SSE ended without idle for %s — polling HTTP", sid)
                wait_session_idle(client, sid, timeout=7200, token=token)
        except Exception:
            # Let finally block clean up, then re-raise
            raise

        if not oc_jobs.is_token_active(token):
            return

        # ---- Enter chat loop ----
        chat_queue = FollowUpQueue(sid, timeout=chat_timeout)
        _register_chat(sid, chat_queue)
        _latch_pending_questions(client, chat_queue, sid, job)

        while oc_jobs.is_token_active(token):
            try:
                follow_up = chat_queue.get()
            except Exception:  # queue.Empty on timeout
                logger.info("[opencode_background] chat timeout for %s — ending", sid)
                break

            if FollowUpQueue.is_end(follow_up):
                logger.info("[opencode_background] chat end signal for %s", sid)
                break

            follow_up = (follow_up or "").strip()
            if not follow_up:
                continue

            # If OpenCode asked a question, the user's utterance is the answer.
            question_id, _qtext = chat_queue.take_question()
            if question_id:
                try:
                    client.reply_question(question_id, answers=[follow_up])
                    logger.info(
                        "[opencode_background] answered question %s for %s",
                        question_id,
                        sid,
                    )
                    _emit_progress(
                        {
                            **job,
                            "phase": "question_answered",
                            "request_id": question_id,
                            "answer": follow_up,
                        }
                    )
                except Exception as exc:
                    logger.exception(
                        "[opencode_background] reply_question %s: %s", question_id, exc
                    )
                relay.reset()
                continue

            logger.info("[opencode_background] chat follow-up for %s: %.60s", sid, follow_up)

            # Reset relay for new turn
            relay.reset()

            # Send follow-up
            try:
                client.prompt_async(sid, text=follow_up, model=model, agent=DEFAULT_AGENT)
                idle = subscriber.wait_until_idle(timeout=120)
                if not idle:
                    if not oc_jobs.is_token_active(token):
                        break
                    logger.info("[opencode_background] chat follow-up SSE lost for %s — polling HTTP", sid)
                    wait_session_idle(client, sid, timeout=7200, token=token)
            except Exception as exc:
                logger.exception("[opencode_background] chat follow-up error for %s: %s", sid, exc)
                # Don't crash the chat loop — log and continue
                continue

            # Surface any new questions OpenCode asked during this turn.
            _latch_pending_questions(client, chat_queue, sid, job)

        # ---- Chat ended — collect final result ----
        _unregister_chat(sid)
        chat_queue = None

        try:
            children = client.session_children(sid) or []
            if children:
                oc_trace.note_subagents(token, children)
        except Exception:
            pass

        result = _fetch_last_message(client, sid, relay, goal=goal)
        if not result:
            raise RuntimeError(
                "OpenCode produced no assistant reply. "
                "Check model/provider config (opencode_control status) "
                "and serve log (memory/opencode_serve.log)."
            )
        reply = extract_message_text(result if isinstance(result, dict) else {})
        voice = format_voice_reply(result if isinstance(result, dict) else {}, session_id=sid)
        oc_flow.record_turn(load_state, save_state, action=action, goal=goal, reply=reply, session_id=sid)
        block = f"[{action}] COMPLETE job_token={token}\n\n{voice}"
        _notify(block, token=token, meta={**meta, "phase": "complete"})
        _emit_progress({**job, "phase": "complete", "error": ""})
        oc_jobs.finish(token, phase="complete")
        oc_jobs.mark_inactive(token)
        try:
            oc_trace.remove(token)
        except Exception:
            pass

    except Exception as exc:
        logger.exception("[opencode_background] chat: %s", exc)
        if chat_queue:
            _unregister_chat(sid)
        if relay:
            relay.close()
        if subscriber:
            subscriber.stop()
        if oc_jobs.is_token_active(token):
            meta_data = _job_meta(job or {"token": token, "goal": goal, "session_id": sid, "workspace": str(ws), "action": action})
            err = classify_opencode_error(exc, job or None)
            _notify(f"[{action}] ERROR job_token={token} ({err['category']})\n\n{err['message']}", token=token, meta={**meta_data, "phase": "error"})
            _emit_progress({**meta_data, "phase": "error", "error": str(exc)})
            oc_jobs.finish(token, phase="error", error=str(exc))
            oc_jobs.mark_inactive(token)
    finally:
        if sid:
            set_active_session(sid)


def launch(
    *,
    goal: str,
    ws: Path,
    action: str = "send",
    session_id: str = "",
    new_session: bool = False,
    parallel: bool = False,
) -> str:
    set_active_workspace(ws)
    ws_resolved = _ws_key(ws)
    if new_session:
        set_active_session("")
    sid = (session_id or "").strip()
    if not sid and not new_session:
        state = load_state()
        active_ws = (state.get("active_workspace") or "").strip()
        if active_ws == ws_resolved:
            sid = (state.get("active_session_id") or "").strip()

    # Resolve session synchronously before spawning the worker thread.
    # This prevents a race where two rapid commands (task + send with parallel=True)
    # both see sid="" and create independent sessions (session fragmentation).
    if not sid and not new_session:
        try:
            client = ensure_server(ws)
            sid = _resolve_session_id(
                client, ws, session_id="", new_session=False, goal=goal
            )
            set_active_session(sid)
        except Exception:
            logger.exception("[opencode_background] session creation in launch")

    with _job_lock:
        if parallel:
            if oc_jobs.count_running() >= MAX_PARALLEL_JOBS:
                return (
                    f"[{action}] ERROR\n\n"
                    f"Max parallel OpenCode jobs ({MAX_PARALLEL_JOBS}) reached. "
                    "Use jobs_list / job_cancel first."
                )
        else:
            if sid:
                fg = oc_jobs.foreground_token()
                fg_job = oc_jobs.get(fg) if fg else {}
                prev_sid = str(fg_job.get("session_id") or "")
                if prev_sid and prev_sid != sid:
                    _abort_foreground()
            else:
                _abort_foreground()

        token = str(time.time_ns())
        oc_jobs.mark_active(token)
        if not parallel:
            _reset_reply_state()
            try:
                oc_trace.reset(token)
            except Exception:
                pass

        job = {
            "token": token,
            "action": action,
            "goal": goal[:500],
            "workspace": str(ws),
            "session_id": sid,
            "parallel": parallel,
            "new_session": new_session,
            "track_subagents": True,
            "starting": True,
            "started_at": time.time(),
            "phase": "starting",
        }
        oc_jobs.register(job)
        _emit_job_started(job)

    threading.Thread(
        target=_worker,
        kwargs={
            "goal": goal,
            "ws": ws,
            "action": action,
            "token": token,
            "session_id": sid,
            "new_session": new_session,
            "parallel": parallel,
        },
        daemon=True,
        name=f"opencode-{token[-6:]}",
    ).start()
    lines = [
        f"[{action}] STARTED",
        "",
        f"workspace: {ws}",
        f"job_token: {token}",
        f"parallel: {parallel}",
        "",
        "SILENT: Do not speak to the user yet. OpenCode is working in background.",
        "Trace is in [OPENCODE LIVE]. You will get one OPENCODE SAYS inject when done — relay that once, briefly.",
    ]
    if sid:
        lines.append(f"session: {sid}")
    running = oc_jobs.count_running()
    if running > 1:
        lines.append(f"running_jobs: {running}")
    return "\n".join(lines)


def launch_chat(
    *,
    goal: str,
    ws: Path,
    action: str = "chat",
    session_id: str = "",
    new_session: bool = False,
    parallel: bool = False,
    chat_timeout: float = 900.0,
) -> str:
    set_active_workspace(ws)
    ws_resolved = _ws_key(ws)
    if new_session:
        set_active_session("")
    sid = (session_id or "").strip()
    if not sid and not new_session:
        state = load_state()
        active_ws = (state.get("active_workspace") or "").strip()
        if active_ws == ws_resolved:
            sid = (state.get("active_session_id") or "").strip()

    if not sid and not new_session:
        try:
            client = ensure_server(ws)
            sid = _resolve_session_id(client, ws, session_id="", new_session=False, goal=goal)
            set_active_session(sid)
        except Exception:
            logger.exception("[opencode_background] chat session creation")

    with _job_lock:
        if parallel:
            if oc_jobs.count_running() >= MAX_PARALLEL_JOBS:
                return (
                    f"[{action}] ERROR\n\n"
                    f"Max parallel OpenCode jobs ({MAX_PARALLEL_JOBS}) reached. "
                    "Use jobs_list / job_cancel first."
                )
        else:
            if sid:
                fg = oc_jobs.foreground_token()
                fg_job = oc_jobs.get(fg) if fg else {}
                prev_sid = str(fg_job.get("session_id") or "")
                if prev_sid and prev_sid != sid:
                    _abort_foreground()
            else:
                _abort_foreground()

        token = str(time.time_ns())
        oc_jobs.mark_active(token)
        if not parallel:
            _reset_reply_state()
            try:
                oc_trace.reset(token)
            except Exception:
                pass

        job = {
            "token": token,
            "action": action,
            "goal": goal[:500],
            "workspace": str(ws),
            "session_id": sid,
            "parallel": parallel,
            "new_session": new_session,
            "mode": "chat",
            "chat_timeout": chat_timeout,
            "track_subagents": True,
            "starting": True,
            "started_at": time.time(),
            "phase": "starting",
        }
        oc_jobs.register(job)
        _emit_job_started(job)

    threading.Thread(
        target=_chat_worker,
        kwargs={
            "goal": goal,
            "ws": ws,
            "action": action,
            "token": token,
            "session_id": sid,
            "new_session": new_session,
            "parallel": parallel,
            "chat_timeout": chat_timeout,
        },
        daemon=True,
        name=f"opencode-chat-{token[-6:]}",
    ).start()
    lines = [
        f"[{action}] STARTED",
        "",
        f"workspace: {ws}",
        f"job_token: {token}",
        f"parallel: {parallel}",
        "",
        "SILENT: Do not speak to the user yet. OpenCode is working in background.",
        "Use follow_up to send messages to this chat session.",
    ]
    if sid:
        lines.append(f"session: {sid}")
    running = oc_jobs.count_running()
    if running > 1:
        lines.append(f"running_jobs: {running}")
    return "\n".join(lines)


launch_task = launch
start_task_async = launch
launch_chat_task = launch_chat


def cancel_job(job_token: str = "") -> str:
    token = oc_jobs.resolve_token(job_token) if job_token else oc_jobs.foreground_token()
    if not token:
        clear_pending()
        return "Nothing to cancel."
    job = oc_jobs.get(token)
    sid = str(job.get("session_id") or "")
    if sid:
        chat_q = get_chat_queue(sid)
        if chat_q:
            chat_q.signal_end()
    if sid:
        ws = str(job.get("workspace") or "").strip()
        alive = False
        if ws:
            servers = _servers_map()
            entry = servers.get(ws) or {}
            if entry.get("url") and _server_alive(str(entry.get("url") or "")):
                alive = True
        else:
            alive = True
        if alive:
            try:
                client = _client_for_job(job)
                client.abort_session(sid)
                client.delete_session(sid)
            except Exception as exc:
                logger.debug("[opencode_background] cancel abort: %s", exc)
    oc_jobs.remove(token)
    try:
        oc_trace.remove(token)
    except Exception:
        pass
    if load_state().get("active_session_id") == sid:
        set_active_session("")
    _emit_progress(
        {
            "token": token,
            "phase": "cancelled",
            "goal": str(job.get("goal") or ""),
            "parallel": bool(job.get("parallel")),
        }
    )
    goal = str(job.get("goal") or "")[:50]
    short = token[-10:] if len(token) > 10 else token
    return (
        f"[job_cancel] OK\n\n"
        f"Stopped 1 job ({short}): {goal or '(no goal)'}"
    )


def cancel_all_jobs() -> str:
    before = oc_jobs.count_running()
    tokens = oc_jobs.clear_all()
    cancelled = 0
    for token in tokens:
        try:
            cancel_job(token)
            cancelled += 1
        except Exception:
            pass
    if cancelled:
        _emit_progress({"phase": "cancelled_all", "count": cancelled})
    if cancelled == 0 and before == 0:
        return "[job_cancel_all] OK\n\nNo OpenCode jobs were running."
    return (
        f"[job_cancel_all] OK\n\n"
        f"Stopped {cancelled} OpenCode job(s). Tracker windows closed."
    )


def launch_command(*, label: str, cmd: str, arguments: str, ws: Path) -> str:
    with _job_lock:
        if oc_jobs.count_running() >= MAX_PARALLEL_JOBS:
            return f"[command] ERROR\n\nMax parallel jobs ({MAX_PARALLEL_JOBS})."
        token = str(time.time_ns())
        oc_jobs.mark_active(token)
        _abort_foreground()
        _reset_reply_state()

    def _cmd_worker() -> None:
        sid = ""
        subscriber = None
        relay = None
        job: dict[str, Any] = {}
        try:
            client = ensure_server(ws)
            model = (load_state().get("default_model") or DEFAULT_MODEL).strip()
            if not oc_jobs.is_token_active(token):
                return
            sess = client.create_session(title=label[:80])
            sid = str(sess.get("id") or "")
            set_active_session(sid)
            job = {
                "token": token,
                "action": "command",
                "goal": label[:500],
                "session_id": sid,
                "workspace": str(ws),
                "started_at": time.time(),
                "phase": "running",
            }
            oc_jobs.register(job)
            _emit_progress({**job, "client": client})

            meta = _job_meta(job)

            def _on_reply(reply: str, final: bool, _meta: Meta) -> None:
                if _reply_handler:
                    _reply_handler(reply, final, _meta)

            relay = ReplyRelay(token, _on_reply, meta=meta)

            def _on_event(event_type: str, props: dict) -> None:
                relay.on_event(event_type, props)
                _emit_progress({**job, "event_type": event_type, "properties": props})

            subscriber = EventSubscriber(client, session_id=sid, on_event=_on_event)
            subscriber.start()
            approver = PermissionAutoApprover(
                client,
                mode="always" if load_state().get("auto_approve_permissions") else "gate",
            )
            approver.start()
            result: dict = {}
            try:
                result = client.run_command(
                    sid,
                    command=cmd,
                    arguments=arguments,
                    model=model,
                    agent=DEFAULT_AGENT,
                )
                idle = subscriber.wait_until_idle()
                if not idle:
                    if not oc_jobs.is_token_active(token):
                        return
                    logger.info(
                        "[opencode_background] command SSE ended without idle — polling HTTP"
                    )
                    wait_session_idle(client, sid, timeout=7200, token=token)
            finally:
                approver.stop()
                relay.close()
                subscriber.stop()
            if not oc_jobs.is_token_active(token):
                return
            if not result:
                result = _fetch_last_message(client, sid, relay)
            voice = format_voice_reply(result if isinstance(result, dict) else {}, session_id=sid)
            meta = _job_meta(job)
            _notify(f"[command] COMPLETE job_token={token}\n\n{voice}", token=token, meta=meta)
            _emit_progress({**job, "phase": "complete", "error": ""})
            oc_jobs.finish(token, phase="complete")
            oc_jobs.mark_inactive(token)
        except Exception as exc:
            logger.exception("[opencode_background] command: %s", exc)
            if relay:
                relay.close()
            if subscriber:
                subscriber.stop()
            if oc_jobs.is_token_active(token):
                err = classify_opencode_error(exc, job or None)
                _emit_progress({"phase": "error", "error": str(exc), "session_id": sid, "token": token})
                _notify(f"[command] ERROR job_token={token} ({err['category']})\n\n{err['message']}", token=token)
                oc_jobs.finish(token, phase="error", error=str(exc))
                oc_jobs.mark_inactive(token)

    _emit_job_started(
        {
            "token": token,
            "action": "command",
            "goal": label[:500],
            "workspace": str(ws),
            "started_at": time.time(),
            "phase": "starting",
        }
    )
    threading.Thread(target=_cmd_worker, daemon=True, name=f"opencode-cmd-{token[-6:]}").start()
    return f"[command] STARTED\n\nworkspace: {ws}\njob_token: {token}"


start_command_async = launch_command


def format_status_extra() -> str:
    jobs = oc_jobs.list_jobs(running_only=True)
    if not jobs:
        return ""
    if len(jobs) == 1:
        job = jobs[0]
        age = int(time.time() - float(job.get("started_at") or time.time()))
        return f"working ({age}s): {str(job.get('goal') or '')[:80]}"
    parts = []
    for job in jobs[:6]:
        age = int(time.time() - float(job.get("started_at") or time.time()))
        tok = str(job.get("token") or "")[-8:]
        parts.append(f"{tok} ({age}s): {str(job.get('goal') or '')[:40]}")
    extra = f"{len(jobs)} jobs running — " + "; ".join(parts)
    return extra[:220]
