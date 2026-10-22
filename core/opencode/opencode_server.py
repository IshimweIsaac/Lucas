"""Manage a background ``opencode serve`` instance for Lucas."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from core.logger import get_logger
from core.opencode.opencode_client import OpenCodeClient, OpenCodeError
from core.opencode.opencode_defaults import DEFAULT_AGENT, DEFAULT_MODEL
from core.opencode.opencode_runner import find_opencode
from memory.config_manager import get_base_dir

logger = get_logger(__name__)

_LIVE_PATH = get_base_dir() / "memory" / "opencode_live.json"
_SERVE_LOG = get_base_dir() / "memory" / "opencode_serve.log"
_STARTUP_TIMEOUT = 45.0
_lock = threading.Lock()
_server_start_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_procs: dict[str, subprocess.Popen] = {}


def _tail_log(path: Path, *, max_bytes: int = 4000) -> str:
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _wait_port_free(port: int, *, host: str = "127.0.0.1", timeout: float = 8.0) -> bool:
    if port <= 0:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def _proc_exit_detail(proc: subprocess.Popen) -> str:
    code = proc.returncode
    tail = _tail_log(_SERVE_LOG)
    msg = f"exit code {code}"
    if tail:
        lines = tail.splitlines()[-12:]
        msg += "; recent log:\n" + "\n".join(lines)
    return msg


def _empty_state() -> dict[str, Any]:
    return {
        "server": {
            "running": False,
            "pid": 0,
            "port": 0,
            "url": "",
            "workspace": "",
            "username": "opencode",
            "password_set": False,
        },
        "active_session_id": "",
        "active_workspace": "",
        "auto_approve_permissions": False,
        "default_model": DEFAULT_MODEL,
        "default_agent": DEFAULT_AGENT,
    }


def _is_ephemeral_workspace(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if "/pytest-" in p or "pytest-of-" in p:
        return True
    return bool(p.startswith("/tmp/") and "pytest" in p)


def _sanitize_state(data: dict[str, Any]) -> dict[str, Any]:
    """Drop pytest temp workspaces left over from test runs."""
    active = str(data.get("active_workspace") or "").strip()
    if active and _is_ephemeral_workspace(active):
        data["active_workspace"] = ""
    srv = data.get("server") or {}
    srv_ws = str(srv.get("workspace") or "").strip()
    if srv_ws and _is_ephemeral_workspace(srv_ws):
        lucas_ws = ""
        try:
            lucas_ws = str(get_base_dir().resolve())
        except Exception:
            pass
        servers = data.get("servers") or {}
        if isinstance(servers, dict) and lucas_ws and lucas_ws in servers:
            data["server"] = dict(servers[lucas_ws])
        else:
            srv["workspace"] = ""
            data["server"] = srv
    if isinstance(data.get("servers"), dict):
        data["servers"] = {
            k: v
            for k, v in data["servers"].items()
            if not _is_ephemeral_workspace(str(k))
        }
    return data


def load_state() -> dict[str, Any]:
    with _lock:
        if not _LIVE_PATH.is_file():
            return _empty_state()
        try:
            data = json.loads(_LIVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _empty_state()
    base = _empty_state()
    base.update(data)
    base = _sanitize_state(base)
    base.setdefault("server", {})
    base["server"].setdefault("running", False)
    base["server"].setdefault("username", "opencode")
    return base


def save_state(data: dict[str, Any]) -> None:
    with _lock:
        _LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LIVE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, _LIVE_PATH)


def _pick_port(preferred: int = 4096) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Could not bind a local port for OpenCode server")


def _server_alive(url: str, *, username: str = "opencode", password: str = "") -> bool:
    try:
        client = OpenCodeClient(url, username=username, password=password, timeout=5)
        health = client.health()
        return bool(health.get("healthy"))
    except (OpenCodeError, OSError):
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _auth() -> tuple[str, str]:
    env = os.environ
    return (
        str(env.get("OPENCODE_SERVER_USERNAME") or "opencode"),
        str(env.get("OPENCODE_SERVER_PASSWORD") or ""),
    )


def _client_from_entry(entry: dict[str, Any]) -> OpenCodeClient:
    username, password = _auth()
    return OpenCodeClient(
        str(entry.get("url") or ""),
        username=str(entry.get("username") or username),
        password=password,
        timeout=600,
    )


def _servers_map(state: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    st = state if state is not None else load_state()
    raw = st.get("servers") or {}
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, dict[str, Any]] = {}
    for key, entry in raw.items():
        if isinstance(entry, dict) and entry.get("url"):
            out[str(key)] = dict(entry)
    legacy = st.get("server") or {}
    legacy_ws = str(legacy.get("workspace") or "").strip()
    if legacy_ws and legacy.get("url") and legacy_ws not in out:
        out[legacy_ws] = dict(legacy)
    return out


def _save_servers_map(servers: dict[str, dict[str, Any]], *, primary_ws: str = "") -> None:
    state = load_state()
    state["servers"] = servers
    if primary_ws and primary_ws in servers:
        state["server"] = dict(servers[primary_ws])
    elif servers:
        state["server"] = dict(next(iter(servers.values())))
    save_state(state)


def list_servers() -> list[dict[str, Any]]:
    username, password = _auth()
    rows: list[dict[str, Any]] = []
    to_remove: list[str] = []
    for ws, entry in _servers_map().items():
        alive = _server_alive(
            str(entry.get("url") or ""),
            username=str(entry.get("username") or username),
            password=password,
        )
        pid = int(entry.get("pid") or 0)
        if pid and not _pid_alive(pid):
            alive = False
        if not alive:
            to_remove.append(ws)
        rows.append(
            {
                "workspace": ws,
                "url": entry.get("url"),
                "port": entry.get("port"),
                "pid": entry.get("pid"),
                "running": alive,
            }
        )
    if to_remove:
        servers = _servers_map()
        for ws in to_remove:
            servers.pop(ws, None)
        _save_servers_map(servers)
    return rows


def get_client(*, require_running: bool = True) -> OpenCodeClient:
    state = load_state()
    srv = state.get("server") or {}
    url = (srv.get("url") or "").strip()
    if not url:
        if require_running:
            raise OpenCodeError("OpenCode server is not running. Use opencode_control server_start.")
        url = "http://127.0.0.1:4096"
    return OpenCodeClient(
        url,
        username=str(srv.get("username") or "opencode"),
        password=str(os.environ.get("OPENCODE_SERVER_PASSWORD") or ""),
        timeout=600,
    )


def server_status() -> dict[str, Any]:
    state = load_state()
    srv = state.get("server") or {}
    url = (srv.get("url") or "").strip()
    running = bool(url) and _server_alive(
        url,
        username=str(srv.get("username") or "opencode"),
        password=str(os.environ.get("OPENCODE_SERVER_PASSWORD") or ""),
    )
    if srv.get("pid") and not _pid_alive(int(srv["pid"])):
        running = False
    srv["running"] = running
    state["server"] = srv
    save_state(state)
    return state


def stop_server() -> str:
    global _proc
    state = load_state()
    srv = state.get("server") or {}
    pid = int(srv.get("pid") or 0)

    stopped = False
    for key in list(_procs):
        p = _procs[key]
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
            stopped = True
    _procs.clear()

    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _proc.kill()
        stopped = True
        _proc = None

    if pid and _pid_alive(pid):
        try:
            os.kill(pid, 15)
            time.sleep(0.5)
            if _pid_alive(pid):
                os.kill(pid, 9)
            stopped = True
        except OSError as exc:
            logger.warning("[opencode_server] stop pid %s: %s", pid, exc)

    port = int(srv.get("port") or 0)
    if port:
        _wait_port_free(port, timeout=6)

    prev = load_state()
    state = _empty_state()
    state["auto_approve_permissions"] = bool(prev.get("auto_approve_permissions", False))
    state["default_model"] = prev.get("default_model") or ""
    state["default_agent"] = prev.get("default_agent") or "build"
    state["active_workspace"] = prev.get("active_workspace") or ""
    save_state(state)
    return "OpenCode server stopped." if stopped else "OpenCode server was not running."


def _start_server_instance(
    workspace: Path,
    *,
    port: int = 0,
    hostname: str = "127.0.0.1",
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Start one ``opencode serve`` for *workspace* (pool-safe)."""
    global _proc

    ws = workspace.expanduser().resolve()
    if not ws.is_dir():
        raise ValueError(f"Workspace not found: {ws}")

    ws_key = str(ws)
    servers = _servers_map()
    username, password = _auth()

    entry = servers.get(ws_key) or {}
    if not replace_existing and entry.get("url") and _server_alive(
        str(entry.get("url") or ""),
        username=str(entry.get("username") or username),
        password=password,
    ):
        _save_servers_map(servers, primary_ws=ws_key)
        state = load_state()
        state["active_workspace"] = ws_key
        save_state(state)
        return state

    bin_path = find_opencode()
    if not bin_path:
        raise RuntimeError("OpenCode binary not found")

    bind_port = port or _pick_port(0)
    if not _wait_port_free(bind_port, timeout=4):
        bind_port = _pick_port(0)

    env = os.environ.copy()
    cmd = [
        bin_path,
        "serve",
        "--port",
        str(bind_port),
        "--hostname",
        hostname,
    ]

    _SERVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_SERVE_LOG, "w", encoding="utf-8") as log_fh:
        log_fh.write(
            f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} cwd={ws} port={bind_port} ---\n"
        )
        log_fh.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(ws),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

    for key in list(_procs):
        dead = _procs[key]
        if dead.poll() is not None:
            del _procs[key]
    _procs[ws_key] = proc
    _proc = proc

    url = f"http://{hostname}:{bind_port}"
    deadline = time.time() + _STARTUP_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"OpenCode server exited during startup ({_proc_exit_detail(proc)})"
            )
        if _server_alive(url, username=username, password=password):
            break
        time.sleep(0.25)
    else:
        if proc.poll() is None:
            proc.kill()
        detail = (
            _proc_exit_detail(proc) if proc.poll() is not None else "still running but unhealthy"
        )
        raise RuntimeError(f"OpenCode server did not become healthy at {url} ({detail})")

    servers[ws_key] = {
        "running": True,
        "pid": proc.pid,
        "port": bind_port,
        "url": url,
        "workspace": ws_key,
        "username": username,
        "password_set": bool(password),
    }
    _save_servers_map(servers, primary_ws=ws_key)

    state = load_state()
    state["active_workspace"] = ws_key
    save_state(state)

    try:
        client = _client_from_entry(servers[ws_key])
        model = (state.get("default_model") or DEFAULT_MODEL).strip()
        client.patch_config({"model": model, "default_agent": DEFAULT_AGENT})
        state["default_model"] = model
        state["default_agent"] = DEFAULT_AGENT
        save_state(state)
    except Exception as exc:
        logger.warning("[opencode_server] config patch: %s", exc)

    return load_state()


def start_server(
    workspace: Path,
    *,
    port: int = 0,
    hostname: str = "127.0.0.1",
) -> dict[str, Any]:
    """Start ``opencode serve`` rooted at *workspace* (adds to pool)."""
    return _start_server_instance(workspace, port=port, hostname=hostname, replace_existing=False)


class PermissionAutoApprover:
    """Background loop that approves pending OpenCode permission prompts.

    Modes:
      - "always": auto-approve every pending request (legacy blind approval).
      - "once": approve each pending request once.
      - "reject": reject every pending request.
      - "gate": do NOT auto-reply — collect the requests so Lucas can relay
        them to the user for voice allow/deny (see ``pending_permissions()``).
    """

    def __init__(self, client: OpenCodeClient, *, mode: str = "gate"):
        self.client = client
        self.mode = mode if mode in ("once", "always", "reject", "gate") else "gate"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="oc-perm")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                pending = self.client.list_permissions()
                set_pending_permissions(pending)
                if self.mode == "gate":
                    # Collect only — leave requests pending for user decision.
                    pass
                else:
                    for req in pending:
                        if not isinstance(req, dict):
                            continue
                        req_id = str(req.get("id") or "")
                        if req_id.startswith("per"):
                            reply = "once" if self.mode == "once" else self.mode
                            self.client.reply_permission(req_id, reply=reply)
            except OpenCodeError:
                pass
            self._stop.wait(2.0)


_pending_permissions: list[dict[str, Any]] = []
_pending_permissions_lock = threading.Lock()


def set_pending_permissions(pending: list[dict[str, Any]]) -> None:
    """Store the latest snapshot of pending permission requests (gate mode)."""
    global _pending_permissions
    clean = [
        dict(p)
        for p in pending
        if isinstance(p, dict) and str(p.get("id") or "")
    ]
    with _pending_permissions_lock:
        _pending_permissions = clean


def pending_permissions() -> list[dict[str, Any]]:
    """Return the latest pending permission requests observed by any gate."""
    with _pending_permissions_lock:
        return [dict(p) for p in _pending_permissions]


class PermissionGate:
    """Collects pending OpenCode permission requests without auto-approving.

    Polls ``list_permissions()`` and refreshes the shared
    ``pending_permissions()`` snapshot; optionally invokes *on_request* with the
    new snapshot so background workers can surface requests to the user.
    """

    def __init__(self, client: OpenCodeClient, *, on_request=None):
        self.client = client
        self._on_request = on_request
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="oc-perm-gate")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def pending(self) -> list[dict[str, Any]]:
        return pending_permissions()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                pending = self.client.list_permissions()
                set_pending_permissions(pending)
                if self._on_request:
                    try:
                        self._on_request(pending_permissions())
                    except Exception:
                        pass
            except OpenCodeError:
                pass
            self._stop.wait(2.0)


def ensure_server(workspace: Path) -> OpenCodeClient:
    ws = workspace.expanduser().resolve()
    ws_key = str(ws)
    username, password = _auth()
    with _server_start_lock:
        servers = _servers_map()
        entry = servers.get(ws_key) or {}
        if entry.get("url") and _server_alive(
            str(entry.get("url") or ""),
            username=str(entry.get("username") or username),
            password=password,
        ):
            _save_servers_map(servers, primary_ws=ws_key)
            state = load_state()
            state["active_workspace"] = ws_key
            save_state(state)
            return _client_from_entry(entry)
        start_server(ws)
    servers = _servers_map()
    entry = servers.get(ws_key) or {}
    if entry.get("url"):
        _save_servers_map(servers, primary_ws=ws_key)
        state = load_state()
        state["active_workspace"] = ws_key
        save_state(state)
        return _client_from_entry(entry)
    raise RuntimeError(f"Failed to start OpenCode server for {ws}")

def set_active_workspace(path: Path) -> None:
    state = load_state()
    state["active_workspace"] = str(path.expanduser().resolve())
    save_state(state)


def set_active_session(session_id: str) -> None:
    state = load_state()
    state["active_session_id"] = session_id
    save_state(state)


def get_active_session() -> str:
    return str(load_state().get("active_session_id") or "")
