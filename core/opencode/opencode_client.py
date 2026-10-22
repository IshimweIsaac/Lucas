"""HTTP client for the OpenCode headless server (OpenAPI)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)


class OpenCodeError(RuntimeError):
    """OpenCode HTTP API error."""

    def __init__(self, message: str, *, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def parse_model(model: str) -> dict[str, str]:
    """Convert ``provider/model`` to OpenCode message model object."""
    raw = (model or "").strip()
    if not raw:
        raise ValueError("model is required (provider/model)")
    if "/" not in raw:
        raise ValueError(f"Invalid model {raw!r}; expected provider/model")
    provider_id, model_id = raw.split("/", 1)
    if not provider_id or not model_id:
        raise ValueError(f"Invalid model {raw!r}; expected provider/model")
    return {"providerID": provider_id, "modelID": model_id}


def extract_message_text(payload: dict[str, Any]) -> str:
    """Pull assistant text parts from a session message response."""
    chunks: list[str] = []
    for part in payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            chunks.append(str(part["text"]).strip())
    return "\n".join(c for c in chunks if c).strip()


def summarize_message(payload: dict[str, Any]) -> str:
    """Human-readable summary of a message response."""
    info = payload.get("info") or {}
    text = extract_message_text(payload)
    lines = [
        f"session: {info.get('sessionID', '?')}",
        f"message: {info.get('id', '?')}",
        f"agent: {info.get('agent', '?')}",
        f"model: {info.get('providerID', '?')}/{info.get('modelID', '?')}",
        f"finish: {info.get('finish', '?')}",
    ]
    tokens = info.get("tokens") or {}
    if tokens:
        lines.append(f"tokens: {tokens.get('total', tokens)}")
    cost = info.get("cost")
    if cost is not None:
        lines.append(f"cost: {cost}")
    if text:
        lines.extend(["", text])
    else:
        lines.append("\n(no text parts)")
    return "\n".join(lines)


def format_voice_reply(payload: dict[str, Any], *, session_id: str = "") -> str:
    """Put OpenCode's spoken reply first so Live reads it aloud."""
    text = extract_message_text(payload)
    info = payload.get("info") or {}
    sid = session_id or str(info.get("sessionID") or "")
    parts = [
        f"OPENCODE SAYS: {text}" if text else "OPENCODE SAYS: (no text reply)",
    ]
    if sid:
        parts.append(f"session_id: {sid}")
    model = info.get("providerID") and info.get("modelID")
    if model:
        parts.append(f"model: {info.get('providerID')}/{info.get('modelID')}")
    return "\n".join(parts)


def extract_opencode_says(block: str) -> str:
    """Pull the assistant reply text from a voice/terminal block."""
    text = (block or "").strip()
    if "OPENCODE SAYS:" not in text:
        return ""
    part = text.split("OPENCODE SAYS:", 1)[1]
    for stop in ("session_id:", "model:", "\n\n["):
        if stop in part:
            part = part.split(stop, 1)[0]
    return part.strip()


def format_terminal_reply(block: str) -> str:
    """Format a completion block for Lucas terminal output."""
    text = (block or "").strip()
    if not text:
        return "[LUCAS] 📤 opencode_control → (empty)"

    action = "complete"
    for tag in ("send", "task", "command"):
        if f"[{tag}] COMPLETE" in text:
            action = tag
            break
        if f"[{tag}] ERROR" in text:
            return f"[LUCAS] 📤 opencode_control → [{tag}] ERROR\n\n{text[:1200]}"

    says = extract_opencode_says(text)
    if says:
        return f"[LUCAS] 📤 opencode_control → [{action}] COMPLETE\n\nOPENCODE SAYS: {says}"
    return f"[LUCAS] 📤 opencode_control → {text[:1200]}"


class OpenCodeClient:
    """Thin wrapper around ``opencode serve`` HTTP endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str = "opencode",
        password: str = "",
        timeout: int = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        query: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            qs = urllib.parse.urlencode({k: v for k, v in query.items() if v})
            if qs:
                url = f"{url}?{qs}"

        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        if self.password:
            import base64

            token = base64.b64encode(
                f"{self.username}:{self.password}".encode("utf-8")
            ).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")

        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise OpenCodeError(
                f"OpenCode {method} {path} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except urllib.error.URLError as exc:
            raise OpenCodeError(f"OpenCode unreachable at {self.base_url}: {exc}") from exc

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # --- global / config -------------------------------------------------

    def health(self) -> dict[str, Any]:
        out = self._request("GET", "/global/health", timeout=10)
        return out if isinstance(out, dict) else {"healthy": False}

    def get_config(self) -> dict[str, Any]:
        out = self._request("GET", "/config", timeout=15)
        return out if isinstance(out, dict) else {}

    def patch_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        out = self._request("PATCH", "/config", body=patch, timeout=15)
        return out if isinstance(out, dict) else {}

    def config_providers(self) -> dict[str, Any]:
        out = self._request("GET", "/config/providers", timeout=30)
        return out if isinstance(out, dict) else {}

    def list_providers(self) -> dict[str, Any]:
        out = self._request("GET", "/provider", timeout=30)
        return out if isinstance(out, dict) else {}

    def provider_auth_methods(self) -> dict[str, Any]:
        out = self._request("GET", "/provider/auth", timeout=30)
        return out if isinstance(out, dict) else {}

    def set_auth(self, provider_id: str, payload: dict[str, Any]) -> bool:
        out = self._request("PUT", f"/auth/{provider_id}", body=payload, timeout=15)
        return bool(out)

    def remove_auth(self, provider_id: str) -> bool:
        out = self._request("DELETE", f"/auth/{provider_id}", timeout=15)
        return bool(out)

    # --- agents / commands / mcp ----------------------------------------

    def list_agents(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/agent", timeout=15)
        return out if isinstance(out, list) else []

    def list_commands(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/command", timeout=15)
        return out if isinstance(out, list) else []

    def mcp_status(self) -> dict[str, Any]:
        out = self._request("GET", "/mcp", timeout=15)
        return out if isinstance(out, dict) else {}

    def mcp_add(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        out = self._request("POST", "/mcp", body={"name": name, "config": config}, timeout=30)
        return out if isinstance(out, dict) else {}

    # --- sessions --------------------------------------------------------

    def list_sessions(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/session", timeout=20)
        return out if isinstance(out, list) else []

    def session_status(self) -> dict[str, Any]:
        out = self._request("GET", "/session/status", timeout=15)
        return out if isinstance(out, dict) else {}

    def create_session(self, *, title: str = "", parent_id: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if parent_id:
            body["parentID"] = parent_id
        out = self._request("POST", "/session", body=body, timeout=20)
        return out if isinstance(out, dict) else {}

    def get_session(self, session_id: str) -> dict[str, Any]:
        out = self._request("GET", f"/session/{session_id}", timeout=15)
        return out if isinstance(out, dict) else {}

    def delete_session(self, session_id: str) -> bool:
        out = self._request("DELETE", f"/session/{session_id}", timeout=20)
        return bool(out)

    def patch_session(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        out = self._request("PATCH", f"/session/{session_id}", body=patch, timeout=15)
        return out if isinstance(out, dict) else {}

    def abort_session(self, session_id: str) -> bool:
        out = self._request("POST", f"/session/{session_id}/abort", body={}, timeout=15)
        return bool(out)

    def session_diff(self, session_id: str, *, message_id: str = "") -> list[dict[str, Any]]:
        query = {"messageID": message_id} if message_id else None
        out = self._request("GET", f"/session/{session_id}/diff", query=query, timeout=30)
        return out if isinstance(out, list) else []

    def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 0,
        missing_ok: bool = False,
    ) -> list[dict[str, Any]]:
        query = {"limit": str(limit)} if limit else None
        try:
            out = self._request(
                "GET", f"/session/{session_id}/message", query=query, timeout=30
            )
        except OpenCodeError as exc:
            if missing_ok and exc.status == 404:
                return []
            raise
        return out if isinstance(out, list) else []

    def send_message(
        self,
        session_id: str,
        *,
        text: str,
        model: str = "",
        agent: str = "",
        system: str = "",
        files: list[str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for path in files or []:
            p = (path or "").strip()
            if p:
                parts.append({"type": "file", "url": f"file://{p}"})

        body: dict[str, Any] = {"parts": parts}
        if model:
            body["model"] = parse_model(model)
        if agent:
            body["agent"] = agent
        if system:
            body["system"] = system

        out = self._request(
            "POST",
            f"/session/{session_id}/message",
            body=body,
            timeout=timeout or self.timeout,
        )
        return out if isinstance(out, dict) else {}

    def prompt_async(
        self,
        session_id: str,
        *,
        text: str,
        model: str = "",
        agent: str = "",
    ) -> None:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if model:
            body["model"] = parse_model(model)
        if agent:
            body["agent"] = agent
        self._request(
            "POST",
            f"/session/{session_id}/prompt_async",
            body=body,
            timeout=60,
        )

    def run_command(
        self,
        session_id: str,
        *,
        command: str,
        arguments: str = "",
        model: str = "",
        agent: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "command": command,
            "arguments": arguments,
        }
        if model:
            body["model"] = parse_model(model)
        if agent:
            body["agent"] = agent
        out = self._request(
            "POST",
            f"/session/{session_id}/command",
            body=body,
            timeout=300,
        )
        return out if isinstance(out, dict) else {}

    def run_shell(
        self,
        session_id: str,
        *,
        command: str,
        agent: str = "build",
        model: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"command": command, "agent": agent}
        if model:
            body["model"] = parse_model(model)
        out = self._request(
            "POST",
            f"/session/{session_id}/shell",
            body=body,
            timeout=self.timeout,
        )
        return out if isinstance(out, dict) else {}

    # --- permissions -----------------------------------------------------

    def list_permissions(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/permission", timeout=10)
        return out if isinstance(out, list) else []

    def reply_permission(
        self,
        request_id: str,
        *,
        reply: str = "once",
        message: str = "",
    ) -> bool:
        body: dict[str, Any] = {"reply": reply}
        if message:
            body["message"] = message
        out = self._request(
            "POST",
            f"/permission/{request_id}/reply",
            body=body,
            timeout=10,
        )
        return bool(out)

    def reply_session_permission(
        self,
        session_id: str,
        request_id: str,
        *,
        response: str = "allow",
        remember: bool = False,
    ) -> bool:
        body = {"response": response, "remember": remember}
        out = self._request(
            "POST",
            f"/session/{session_id}/permissions/{request_id}",
            body=body,
            timeout=10,
        )
        return bool(out)

    # --- files / search --------------------------------------------------

    def find_text(self, pattern: str) -> list[dict[str, Any]]:
        out = self._request("GET", "/find", query={"pattern": pattern}, timeout=30)
        return out if isinstance(out, list) else []

    def find_file(self, query: str, *, limit: int = 20) -> list[str]:
        q: dict[str, str] = {}
        if (query or "").strip():
            q["query"] = query.strip()
        if limit:
            q["limit"] = str(limit)
        out = self._request("GET", "/find/file", query=q or None, timeout=20)
        return out if isinstance(out, list) else []

    def list_workspace_files(self, *, limit: int = 80) -> list[str]:
        """List project files — tries OpenCode APIs, skips empty-query 400s."""
        for query in (".", "*"):
            try:
                paths = self.find_file(query, limit=limit)
                if paths:
                    return [str(p) for p in paths]
            except OpenCodeError:
                continue
        try:
            stat = self.file_status()
            paths: list[str] = []
            for item in stat or []:
                if not isinstance(item, dict):
                    continue
                p = item.get("path") or item.get("file") or item.get("name") or ""
                if p:
                    paths.append(str(p))
            if paths:
                return paths[:limit]
        except OpenCodeError:
            pass
        return []

    def read_file(self, path: str) -> dict[str, Any]:
        out = self._request("GET", "/file/content", query={"path": path}, timeout=20)
        return out if isinstance(out, dict) else {}

    def file_status(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/file/status", timeout=20)
        return out if isinstance(out, list) else []

    # --- project / path --------------------------------------------------

    def current_path(self) -> dict[str, Any]:
        out = self._request("GET", "/path", timeout=10)
        return out if isinstance(out, dict) else {}

    def current_project(self) -> dict[str, Any]:
        out = self._request("GET", "/project/current", timeout=10)
        return out if isinstance(out, dict) else {}

    def list_projects(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/project", timeout=20)
        return out if isinstance(out, list) else []

    def vcs_status(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/vcs/status", timeout=20)
        return out if isinstance(out, list) else []

    def vcs_diff(self, *, file_path: str = "") -> Any:
        query = {"path": file_path} if file_path else None
        out = self._request("GET", "/vcs/diff", query=query, timeout=30)
        return out

    def list_skills(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/skill", timeout=15)
        return out if isinstance(out, list) else []

    def list_lsp(self) -> dict[str, Any]:
        out = self._request("GET", "/lsp", timeout=15)
        return out if isinstance(out, dict) else {}

    def list_formatters(self) -> dict[str, Any]:
        out = self._request("GET", "/formatter", timeout=15)
        return out if isinstance(out, dict) else {}

    def find_symbol(self, pattern: str) -> list[dict[str, Any]]:
        out = self._request("GET", "/find/symbol", query={"pattern": pattern}, timeout=30)
        return out if isinstance(out, list) else []

    def list_questions(self) -> list[dict[str, Any]]:
        out = self._request("GET", "/question", timeout=10)
        return out if isinstance(out, list) else []

    def reply_question(self, request_id: str, *, answers: list[str] | None = None) -> bool:
        body: dict[str, Any] = {}
        if answers:
            body["answers"] = answers
        out = self._request(
            "POST",
            f"/question/{request_id}/reply",
            body=body,
            timeout=15,
        )
        return bool(out)

    def reject_question(self, request_id: str) -> bool:
        out = self._request("POST", f"/question/{request_id}/reject", body={}, timeout=15)
        return bool(out)

    def session_todo(self, session_id: str) -> list[dict[str, Any]]:
        out = self._request("GET", f"/session/{session_id}/todo", timeout=15)
        return out if isinstance(out, list) else []

    def session_children(self, session_id: str) -> list[dict[str, Any]]:
        out = self._request("GET", f"/session/{session_id}/children", timeout=15)
        return out if isinstance(out, list) else []

    def get_message(self, session_id: str, message_id: str) -> dict[str, Any]:
        out = self._request(
            "GET",
            f"/session/{session_id}/message/{message_id}",
            timeout=20,
        )
        return out if isinstance(out, dict) else {}

    def session_summarize(self, session_id: str) -> dict[str, Any]:
        out = self._request("POST", f"/session/{session_id}/summarize", body={}, timeout=120)
        return out if isinstance(out, dict) else {}

    def session_revert(self, session_id: str, *, message_id: str = "") -> bool:
        body = {"messageID": message_id} if message_id else {}
        out = self._request("POST", f"/session/{session_id}/revert", body=body, timeout=30)
        return bool(out)

    def session_fork(self, session_id: str, *, message_id: str = "") -> dict[str, Any]:
        body = {"messageID": message_id} if message_id else {}
        out = self._request("POST", f"/session/{session_id}/fork", body=body, timeout=30)
        return out if isinstance(out, dict) else {}

    def mcp_connect(self, name: str) -> dict[str, Any]:
        out = self._request("POST", f"/mcp/{name}/connect", body={}, timeout=60)
        return out if isinstance(out, dict) else {}

    def mcp_disconnect(self, name: str) -> bool:
        out = self._request("POST", f"/mcp/{name}/disconnect", body={}, timeout=15)
        return bool(out)

    def get_logs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        query = {"limit": str(limit)} if limit else None
        out = self._request("GET", "/log", query=query, timeout=15)
        return out if isinstance(out, list) else []
