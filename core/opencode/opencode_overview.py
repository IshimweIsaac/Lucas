"""Deep OpenCode status — everything Lucas needs to understand the runtime."""

from __future__ import annotations

import json
from typing import Any

from core.opencode.opencode_client import OpenCodeClient, extract_message_text
from core.opencode.opencode_defaults import DEFAULT_AGENT, DEFAULT_MODEL
from core.opencode.opencode_server import server_status


def _safe(fn, default: Any = None) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _format_session_brief(sess: dict[str, Any]) -> str:
    if not sess:
        return "(none)"
    model = sess.get("model") or {}
    model_str = ""
    if isinstance(model, dict):
        prov = model.get("providerID") or "?"
        mid = model.get("id") or model.get("modelID") or "?"
        model_str = f"{prov}/{mid}"
    lines = [
        f"id: {sess.get('id', '?')}",
        f"title: {sess.get('title') or sess.get('slug') or '(untitled)'}",
        f"agent: {sess.get('agent', '?')}",
        f"model: {model_str or '?'}",
        f"directory: {sess.get('directory', '?')}",
    ]
    summary = sess.get("summary") or {}
    if isinstance(summary, dict) and summary.get("files"):
        lines.append(
            f"changes: +{summary.get('additions', 0)} -{summary.get('deletions', 0)} "
            f"({summary.get('files', 0)} files)"
        )
    tokens = sess.get("tokens") or {}
    if isinstance(tokens, dict) and tokens.get("input"):
        lines.append(f"tokens: in={tokens.get('input')} out={tokens.get('output', 0)}")
    cost = sess.get("cost")
    if cost:
        lines.append(f"cost: ${cost:.4f}" if isinstance(cost, (int, float)) else f"cost: {cost}")
    return "\n  ".join(lines)


def _format_last_message(msgs: list[dict[str, Any]]) -> str:
    if not msgs:
        return "(no messages)"
    last = msgs[-1]
    info = (last or {}).get("info") or {}
    role = info.get("role", "?")
    finish = info.get("finish", "?")
    text = extract_message_text(last or {})
    preview = (text[:400] + "…") if len(text) > 400 else text
    parts_summary: list[str] = []
    for part in (last or {}).get("parts") or []:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type", "?")
        if ptype in ("tool-invocation", "tool", "tool-result"):
            tool = part.get("tool") or part.get("name") or ptype
            parts_summary.append(f"tool:{tool}")
        elif ptype == "reasoning":
            parts_summary.append("reasoning")
    extra = f" [{', '.join(parts_summary[:6])}]" if parts_summary else ""
    return f"[{role}] finish={finish}{extra}\n  {preview or '(no text)'}"


def _format_permissions(pending: list[dict[str, Any]]) -> str:
    if not pending:
        return "(none pending)"
    lines = []
    for req in pending[:10]:
        if not isinstance(req, dict):
            continue
        lines.append(
            f"- {req.get('id', '?')}: {req.get('permission', '?')} "
            f"{req.get('pattern', '') or req.get('title', '')}"
        )
    return "\n".join(lines)


def _format_questions(questions: list[dict[str, Any]]) -> str:
    if not questions:
        return "(none pending)"
    lines = []
    for q in questions[:5]:
        if not isinstance(q, dict):
            continue
        lines.append(f"- {q.get('id', '?')}: {q.get('question') or q.get('title') or '?'}")
    return "\n".join(lines)


def _format_vcs(files: list[dict[str, Any]], *, max_files: int = 12) -> str:
    if not files:
        return "(clean)"
    lines = []
    for f in files[:max_files]:
        if not isinstance(f, dict):
            continue
        status = f.get("status", "?")
        path = f.get("file", "?")
        adds = f.get("additions", 0)
        dels = f.get("deletions", 0)
        lines.append(f"- [{status}] {path} (+{adds}/-{dels})")
    if len(files) > max_files:
        lines.append(f"… and {len(files) - max_files} more")
    return "\n".join(lines)


def build_overview(
    client: OpenCodeClient,
    *,
    include_messages: bool = True,
    message_limit: int = 5,
) -> str:
    """Aggregate full OpenCode runtime picture for Lucas."""
    state = server_status()
    srv = state.get("server") or {}
    active_sid = state.get("active_session_id") or ""

    sections: list[str] = ["=== OpenCode Deep Overview ==="]

    # Server
    health = _safe(client.health, {})
    sections.append(
        "## Server\n"
        f"running: {srv.get('running')}\n"
        f"url: {srv.get('url') or '(none)'}\n"
        f"workspace: {srv.get('workspace') or '(none)'}\n"
        f"version: {health.get('version', '?')}\n"
        f"healthy: {health.get('healthy', False)}"
    )

    # Config + providers
    cfg = _safe(client.get_config, {})
    prov = _safe(client.list_providers, {})
    connected = prov.get("connected") or []
    sections.append(
        "## Config\n"
        f"model: {cfg.get('model') or state.get('default_model') or DEFAULT_MODEL}\n"
        f"agent: {cfg.get('default_agent') or state.get('default_agent') or DEFAULT_AGENT}\n"
        f"auto_approve: {state.get('auto_approve_permissions', False)}\n"
        f"connected_providers: {', '.join(connected) or '(none)'}"
    )

    # Agents, commands, skills
    agents = _safe(client.list_agents, [])
    agent_names = [a.get("name", "?") for a in agents if isinstance(a, dict)][:12]
    cmds = _safe(client.list_commands, [])
    cmd_names = [c.get("name", "?") for c in cmds if isinstance(c, dict)][:8]
    skills = _safe(client.list_skills, [])
    skill_names = [s.get("name", "?") for s in skills if isinstance(s, dict)][:8]
    sections.append(
        "## Capabilities\n"
        f"agents ({len(agents)}): {', '.join(agent_names) or '(none)'}\n"
        f"commands ({len(cmds)}): {', '.join(cmd_names) or '(none)'}\n"
        f"skills ({len(skills)}): {', '.join(skill_names) or '(none)'}"
    )

    # MCP + LSP
    mcp = _safe(client.mcp_status, {})
    lsp = _safe(client.list_lsp, {})
    sections.append(
        "## Integrations\n"
        f"mcp: {json.dumps(mcp, indent=2)[:1500] if mcp else '(none)'}\n"
        f"lsp: {json.dumps(lsp) if lsp else '(none)'}"
    )

    # Active session
    if active_sid:
        sess = _safe(lambda: client.get_session(active_sid), {})
        sections.append(f"## Active Session\n  {_format_session_brief(sess)}")
        if include_messages:
            msgs = _safe(lambda: client.list_messages(active_sid, limit=message_limit), [])
            sections.append(f"## Last Messages\n{_format_last_message(msgs)}")
        todos = _safe(lambda: client.session_todo(active_sid), [])
        if todos:
            todo_lines = [
                f"- [{'x' if t.get('completed') else ' '}] {t.get('content') or t.get('text') or '?'}"
                for t in todos
                if isinstance(t, dict)
            ]
            sections.append("## Session Todos\n" + ("\n".join(todo_lines) or "(empty)"))
        diff = _safe(lambda: client.session_diff(active_sid), [])
        if diff:
            sections.append(f"## Session Diff\n{json.dumps(diff, indent=2)[:2000]}")
    else:
        sections.append("## Active Session\n(none — use session_create or send/run)")

    # Permissions + questions
    perms = _safe(client.list_permissions, [])
    questions = _safe(client.list_questions, [])
    sections.append(
        f"## Pending Permissions\n{_format_permissions(perms)}\n\n"
        f"## Pending Questions\n{_format_questions(questions)}"
    )

    # VCS + file status
    vcs = _safe(client.vcs_status, [])
    file_stat = _safe(client.file_status, [])
    sections.append(
        f"## VCS Changes ({len(vcs)} files)\n{_format_vcs(vcs)}\n\n"
        f"## File Status\n{json.dumps(file_stat[:8], indent=2)[:1200] if file_stat else '(none)'}"
    )

    # All sessions count
    sessions = _safe(client.list_sessions, [])
    sections.append(f"## Sessions\n{len(sessions)} total; active={active_sid or '(none)'}")

    return "\n\n".join(sections)


def apply_defaults(client: OpenCodeClient, *, force: bool = False) -> dict[str, str]:
    """Ensure OpenCode uses build agent (write-capable) and configured model."""
    from core.opencode.opencode_server import load_state, save_state

    state = load_state()
    model = state.get("default_model") or DEFAULT_MODEL
    agent = DEFAULT_AGENT

    if force or not state.get("default_model"):
        model = DEFAULT_MODEL

    patch: dict[str, Any] = {}
    cfg = _safe(client.get_config, {})
    if force or cfg.get("model") != model:
        patch["model"] = model
    if force or cfg.get("default_agent") != agent:
        patch["default_agent"] = agent

    if patch:
        client.patch_config(patch)

    state["default_model"] = model
    state["default_agent"] = agent
    save_state(state)
    return {"model": model, "agent": agent}
