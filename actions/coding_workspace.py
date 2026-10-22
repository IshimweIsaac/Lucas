"""
Repo-aware coding agent: grep → read → patch → verify loop.

Optimized for weaker models: small context, deterministic tools, lint+test proof,
unified diffs, cached tree, stop when green.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.logger import get_logger
from memory.config_manager import get_base_dir
from memory.coding_model import get_coding_model
from memory.model_router import generate_routed

logger = get_logger(__name__)

BASE_DIR = get_base_dir()
PROFILE_PATH = BASE_DIR / "memory" / "coding_profile.json"

MAX_AGENT_STEPS = 12
MAX_ONE_SHOT_PLAN_STEPS = 10
MAX_REPAIR_PLAN_STEPS = 5
MAX_FAST_FIX_ROUNDS = 2

_DEFAULT_LINT_SCOPED = (
    "python -m ruff check actions tests agent memory core "
    "--output-format=concise"
)
MAX_READ_LINES = 200
MAX_GREP_MATCHES = 60
# Reject whole-file wipe via patch_lines (common Flash-Lite failure mode).
_MAX_PATCH_LINE_SPAN = 60
_MIN_RETAINED_LINE_RATIO = 0.45
TREE_CACHE_TTL_SEC = 300
RATE_LIMIT_WAIT_SEC = 35

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".cursor",
}

# session tree cache: workspace_key -> (monotonic_time, tree_text)
_tree_cache: dict[str, tuple[float, str]] = {}

TOOL_SCHEMA = {
    "name": "coding_workspace",
    "description": (
        "Work inside a project folder: search, read, patch, lint+test. "
        "Search, read, patch, lint, and test code."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "set_workspace | get_profile | status | "
                    "list_dir | grep | read | patch | patch_lines | run. "
                    "run: pass command= for shell (e.g. git describe --tags); "
                    "omit command to run project verify (pytest/cargo)."
                ),
            },
            "workspace_path": {"type": "STRING", "description": "Project root"},
            "path": {"type": "STRING", "description": "Relative file or directory"},
            "pattern": {"type": "STRING", "description": "Regex/text for grep"},
            "glob": {"type": "STRING", "description": "Glob for grep (e.g. *.py)"},
            "start_line": {"type": "INTEGER", "description": "read/patch_lines: first line"},
            "end_line": {"type": "INTEGER", "description": "read/patch_lines: last line"},
            "search": {"type": "STRING", "description": "patch: exact text to find"},
            "replace": {"type": "STRING", "description": "patch: replacement text"},
            "diff": {
                "type": "STRING",
                "description": "patch: unified diff hunks (preferred over search/replace)",
            },
            "command": {"type": "STRING", "description": "run: shell command override"},
            "verify_command": {"type": "STRING", "description": "set_workspace: test cmd"},
            "lint_command": {"type": "STRING", "description": "set_workspace: lint cmd"},
            "tests_only": {
                "type": "BOOLEAN",
                "description": "set_workspace: skip lint, pytest only",
            },
            "verify_mode": {
                "type": "STRING",
                "description": "set_workspace: tests_and_lint | tests_only",
            },
            "content": {
                "type": "STRING",
                "description": "patch_lines: replacement text for line range",
            },
            "coding_model": {
                "type": "STRING",
                "description": "set_workspace: e.g. gemini-3.1-flash-lite (coding quota only)",
            },
            "depth": {"type": "INTEGER", "description": "list_dir depth"},
            "timeout": {
                "type": "INTEGER",
                "description": "run: max seconds to wait (default 30)",
            },
        },
        "required": ["action"],
    },
}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _default_profile() -> dict:
    return {
        "workspace_root": str(BASE_DIR),
        "verify_command": "python -m pytest tests/ -q --tb=line",
        "lint_command": _DEFAULT_LINT_SCOPED,
        "verify_mode": "tests_and_lint",
        "tests_only": False,
        "coding_model": "gemini-3.1-flash-lite",
    }


def _load_profile() -> dict:
    profile = _default_profile()
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                profile.update({k: v for k, v in data.items() if v is not None})
        except Exception as e:
            logger.warning("Failed to load profile: %s", e)
    if not profile.get("workspace_root"):
        profile["workspace_root"] = str(BASE_DIR)
    return profile


def _save_profile(profile: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def _resolve_workspace(explicit: str = "") -> Path:
    if explicit:
        root = Path(explicit).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        else:
            root = root.resolve()
    else:
        prof = _load_profile()
        root = Path(prof.get("workspace_root") or BASE_DIR).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Workspace not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Workspace is not a directory: {root}")
    return root


def _safe_path(workspace: Path, rel: str) -> Path:
    rel = (rel or ".").strip().lstrip("/\\")
    target = (workspace / rel).resolve()
    ws = workspace.resolve()
    if target != ws and not target.is_relative_to(ws):
        raise PermissionError(f"Path escapes workspace: {rel}")
    return target


# ---------------------------------------------------------------------------
# Tree cache
# ---------------------------------------------------------------------------

def _get_cached_tree(workspace: Path, depth: int = 2, *, refresh: bool = False) -> str:
    key = str(workspace.resolve())
    now = time.monotonic()
    if not refresh and key in _tree_cache:
        ts, text = _tree_cache[key]
        if now - ts < TREE_CACHE_TTL_SEC:
            return text
    text = _list_dir(workspace, ".", depth)
    _tree_cache[key] = (now, text)
    return text


def invalidate_tree_cache(workspace: Path | None = None) -> None:
    if workspace is None:
        _tree_cache.clear()
        return
    _tree_cache.pop(str(workspace.resolve()), None)


# ---------------------------------------------------------------------------
# Low-level tools
# ---------------------------------------------------------------------------

def _list_dir(workspace: Path, rel: str = ".", depth: int = 2) -> str:
    root = _safe_path(workspace, rel)
    if not root.exists():
        return f"Not found: {rel}"
    if root.is_file():
        return f"FILE {rel} ({root.stat().st_size} bytes)"

    depth = max(1, min(depth, 4))
    lines: list[str] = []

    def walk(current: Path, level: int, prefix: str) -> None:
        if level > depth:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return
        for entry in entries:
            if entry.name in _SKIP_DIRS and entry.is_dir():
                continue
            rel_name = entry.relative_to(workspace).as_posix()
            if entry.is_dir():
                lines.append(f"{prefix}{rel_name}/")
                walk(entry, level + 1, prefix + "  ")
            else:
                lines.append(f"{prefix}{rel_name}")

    walk(root, 1, "")
    if not lines:
        return f"(empty) {rel}"
    return "\n".join(lines[:400])


def _grep(workspace: Path, pattern: str, glob: str = "") -> str:
    if not pattern:
        return "pattern is required."

    default_glob = glob or "!{.git,__pycache__,node_modules,.venv,venv}/**"
    cmd = [
        "rg", "--line-number", "--max-count", str(MAX_GREP_MATCHES),
        "--glob", default_glob, pattern, str(workspace),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        out = result.stdout.strip()
        if out:
            rel_lines = []
            ws = str(workspace.resolve())
            for line in out.splitlines():
                if line.startswith(ws):
                    line = line[len(ws):].lstrip("/\\")
                rel_lines.append(line)
            return "\n".join(rel_lines[:MAX_GREP_MATCHES])
        if result.returncode == 1:
            return "No matches."
        err = result.stderr.strip()
        return f"grep error: {err[:300]}" if err else "No matches."
    except FileNotFoundError:
        pass

    rx = re.compile(pattern)
    matches: list[str] = []
    for path in workspace.rglob("*"):
        if len(matches) >= MAX_GREP_MATCHES:
            break
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if glob and not path.match(glob):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Failed to read %s: %s", path, e)
            continue
        rel = path.relative_to(workspace).as_posix()
        if rel == "agent/planner.py":
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append(f"{rel}:{i}:{line[:200]}")
                if len(matches) >= MAX_GREP_MATCHES:
                    break
    return "\n".join(matches) if matches else "No matches."


def _read_file(
    workspace: Path,
    rel: str,
    start_line: int = 1,
    end_line: int | None = None,
) -> str:
    path = _safe_path(workspace, rel)
    if not path.is_file():
        return f"Not a file: {rel}"

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line)
    end = end_line if end_line and end_line >= start else start + MAX_READ_LINES - 1
    end = min(end, start + MAX_READ_LINES - 1, len(lines))

    if start > len(lines):
        return f"File has {len(lines)} lines; start_line {start} is past end."

    snippet = [f"{i:4d}| {lines[i - 1]}" for i in range(start, end + 1)]
    return f"--- {rel} (lines {start}-{end} of {len(lines)}) ---\n" + "\n".join(snippet)


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------

@dataclass
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]]  # (tag, content) tag in ' ', '-', '+'


def _parse_unified_hunks(diff: str) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    lines = diff.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            i += 1
            continue
        hunk = _Hunk(
            old_start=int(m.group(1)),
            old_count=int(m.group(2) or 1),
            new_start=int(m.group(3)),
            new_count=int(m.group(4) or 1),
            lines=[],
        )
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            hl = lines[i]
            if hl.startswith((" ", "-", "+")):
                hunk.lines.append((hl[0], hl[1:]))
            elif hl.startswith("\\"):
                pass  # "\ No newline at end of file"
            elif hl.strip() == "":
                pass
            i += 1
        hunks.append(hunk)
    return hunks


def _apply_hunks_to_lines(file_lines: list[str], hunks: list[_Hunk]) -> list[str]:
    result = list(file_lines)
    for hunk in reversed(hunks):
        old_i = hunk.old_start - 1
        new_segment: list[str] = []
        cursor = old_i
        for tag, content in hunk.lines:
            if tag == " ":
                if cursor >= len(result):
                    raise ValueError(f"context line {cursor + 1} past end of file")
                if result[cursor] != content:
                    raise ValueError(
                        f"context mismatch at line {cursor + 1}: "
                        f"expected {content!r}, got {result[cursor]!r}"
                    )
                new_segment.append(content)
                cursor += 1
            elif tag == "-":
                if cursor >= len(result):
                    raise ValueError(f"remove line {cursor + 1} past end of file")
                if result[cursor] != content:
                    raise ValueError(
                        f"remove mismatch at line {cursor + 1}: "
                        f"expected {content!r}, got {result[cursor]!r}"
                    )
                cursor += 1
            elif tag == "+":
                new_segment.append(content)
        result[old_i:cursor] = new_segment
    return result


def _apply_unified_diff(workspace: Path, rel: str, diff: str) -> str:
    if not diff or not diff.strip():
        return "Patch failed: diff is empty."

    path = _safe_path(workspace, rel)
    if not path.is_file():
        return f"Not a file: {rel}"

    # Normalize leading blank line (common after file_controller writes)
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if len(lines) >= 2 and lines[0] == "" and lines[1].strip():
        path.write_text("\n".join(lines[1:]) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")

    body = diff.replace("\r\n", "\n")
    if "@@" not in body:
        return "Patch failed: diff has no @@ hunk headers."

    rel_posix = rel.replace("\\", "/")
    if not body.lstrip().startswith("---"):
        body = f"--- a/{rel_posix}\n+++ b/{rel_posix}\n" + body.lstrip()

    hunks = _parse_unified_hunks(body)
    if not hunks:
        return "Patch failed: could not parse any hunks."

    original = path.read_text(encoding="utf-8")
    file_lines = original.splitlines()

    try:
        new_lines = _apply_hunks_to_lines(file_lines, hunks)
    except ValueError as e:
        return f"Patch failed: {e}"

    path.write_text("\n".join(new_lines) + ("\n" if original.endswith("\n") else ""), encoding="utf-8")
    return f"Patched {rel} (unified diff, {len(hunks)} hunk(s))."


def _apply_search_replace(workspace: Path, rel: str, search: str, replace: str) -> str:
    if not search:
        return "Patch failed: search is empty (use diff or search/replace)."

    path = _safe_path(workspace, rel)
    if not path.is_file():
        return f"Not a file: {rel}"

    content = path.read_text(encoding="utf-8")
    count = content.count(search)
    if count == 0:
        return (
            f"Patch failed: search text not found in {rel}. "
            "Use read first, or use a unified diff."
        )
    if count > 1:
        return f"Patch failed: search appears {count} times in {rel}. Use diff or more context."

    path.write_text(content.replace(search, replace, 1), encoding="utf-8")
    return f"Patched {rel} (search/replace)."


def _apply_patch_lines(
    workspace: Path,
    rel: str,
    start_line: int,
    end_line: int,
    content: str,
) -> str:
    """Replace inclusive line range with content (use after read with line numbers)."""
    if not rel:
        return "path is required for patch_lines."
    if start_line < 1:
        return "Patch failed: start_line must be >= 1."

    path = _safe_path(workspace, rel)
    if not path.is_file():
        return f"Not a file: {rel}"

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return f"Patch failed: {rel} is empty."

    end = end_line if end_line and end_line >= start_line else start_line
    end = min(end, len(lines))
    start = min(start_line, len(lines))

    span = end - start + 1
    new_block = content.splitlines() if content else []
    if span > _MAX_PATCH_LINE_SPAN and len(new_block) < int(span * _MIN_RETAINED_LINE_RATIO):
        return (
            f"Patch rejected: patch_lines would replace {span} lines of {rel} with only "
            f"{len(new_block)} lines. Use read on a small range, then patch_lines for "
            f"≤{_MAX_PATCH_LINE_SPAN} lines, or use patch with a unified diff."
        )
    if start == 1 and end >= max(len(lines) - 2, 1) and len(new_block) < len(lines) // 2:
        return (
            f"Patch rejected: near full-file patch_lines on {rel} "
            f"({span}/{len(lines)} lines). Use patch with @@ hunks instead."
        )
    updated = lines[: start - 1] + new_block + lines[end:]
    original = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(updated) + ("\n" if original.endswith("\n") else ""),
        encoding="utf-8",
    )
    return (
        f"Patched {rel} (lines {start}-{end} → {len(new_block)} line(s))."
    )


def _apply_patch(
    workspace: Path,
    rel: str,
    search: str = "",
    replace: str = "",
    diff: str = "",
) -> str:
    if not rel:
        return "path is required for patch."
    if diff and diff.strip():
        return _apply_unified_diff(workspace, rel, diff)
    return _apply_search_replace(workspace, rel, search, replace)


# ---------------------------------------------------------------------------
# Commands & verify
# ---------------------------------------------------------------------------

def _run_command_raw(workspace: Path, command: str, timeout: int = 30) -> tuple[int, str]:
    if not command or not command.strip():
        return 1, "No command provided."

    cmd = command.strip()
    use_shell = any(tok in cmd for tok in ("|", "&&", "||", ";", ">", "<"))

    if use_shell:
        run_args: list[str] | str = cmd
        shell = True
    else:
        try:
            parts = shlex.split(cmd)
        except ValueError:
            parts = cmd.split()
        if parts[0].lower() == "python":
            parts[0] = sys.executable
        run_args = parts
        shell = False

    try:
        process = subprocess.Popen(
            run_args,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(workspace),
        )
        try:
            out, err = process.communicate(timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate(timeout=5)
            code = -1
    except FileNotFoundError as e:
        return 127, f"Command not found: {e}"

    out = out.strip()
    err = err.strip()
    sections = []
    if code == -1:
        sections.append(f"exit_code: killed (timeout after {timeout}s)")
    else:
        sections.append(f"exit_code: {code}")
    sections.append(f"command: {command}")
    if out:
        sections.append(f"STDOUT:\n{out[:8000]}")
    if err:
        sections.append(f"STDERR:\n{err[:8000]}")
    if not out and not err:
        sections.append("(no output)")
    return code, "\n\n".join(sections)



def _run_command(workspace: Path, command: str, timeout: int = 120) -> str:
    _, text = _run_command_raw(workspace, command, timeout)
    return text


def _lint_skipped_message(stderr: str) -> bool:
    low = stderr.lower()
    return "no module named ruff" in low or "ruff: command not found" in low


def _workspace_supports_lint(workspace: Path) -> bool:
    """Ruff on a random scratch folder usually fails — only lint real projects."""
    markers = ("pyproject.toml", "setup.py", "setup.cfg", "ruff.toml", ".ruff.toml")
    if any((workspace / m).exists() for m in markers):
        return True
    # Lucas repo layout
    return (workspace / "tests").is_dir() and (workspace / "actions").is_dir()


def _lint_skipped(profile: dict) -> bool:
    if profile.get("tests_only") is True:
        return True
    mode = (profile.get("verify_mode") or "tests_and_lint").strip().lower()
    return mode in ("tests_only", "tests", "pytest_only")


def _project_kind(workspace: Path) -> str:
    if (workspace / "Cargo.toml").is_file():
        return "rust"
    if (workspace / "actions").is_dir() and (workspace / "tests").is_dir():
        return "lucas_python"
    if (workspace / "pyproject.toml").is_file() or (workspace / "setup.py").is_file():
        return "python"
    return "generic"


def _infer_project_profile(workspace: Path) -> dict:
    """Suggest verify/lint settings when switching workspace."""
    kind = _project_kind(workspace)
    if kind == "rust":
        return {
            "verify_command": "cargo check -q",
            "lint_command": "",
            "tests_only": True,
            "verify_mode": "tests_only",
            "project_kind": "rust",
        }
    if kind == "lucas_python":
        return {
            "verify_command": "python -m pytest tests/ -q --tb=line",
            "lint_command": _DEFAULT_LINT_SCOPED,
            "tests_only": False,
            "verify_mode": "tests_and_lint",
            "project_kind": "lucas_python",
        }
    if kind == "python":
        return {
            "verify_command": "python -m pytest -q --tb=line",
            "lint_command": "",
            "tests_only": True,
            "verify_mode": "tests_only",
            "project_kind": "python",
        }
    return {"project_kind": "generic"}


def _resolve_test_command(workspace: Path, profile: dict) -> str:
    cmd = (profile.get("verify_command") or "").strip()
    if not cmd:
        return ""
    kind = _project_kind(workspace)
    if kind == "rust":
        if "cargo" in cmd:
            return cmd
        return "cargo check -q"
    if "pytest" in cmd:
        if kind == "lucas_python":
            return cmd
        if (workspace / "tests").is_dir():
            return cmd
        return ""
    return cmd


def _run_verify(workspace: Path, profile: dict) -> tuple[bool, str]:
    """Lint then tests. Returns (all_passed, formatted_output)."""
    parts: list[str] = []
    all_ok = True

    lint_cmd = (profile.get("lint_command") or "").strip()
    if _lint_skipped(profile):
        parts.append("=== lint ===\n(skipped — tests_only / verify_mode)")
    elif lint_cmd and not _workspace_supports_lint(workspace):
        parts.append(
            "=== lint ===\n(skipped — workspace is not a full Python project; "
            "use the Lucas repo for lint+test challenges)"
        )
    elif lint_cmd:
        code, out = _run_command_raw(workspace, lint_cmd)
        parts.append(f"=== lint ===\n{out}")
        if code != 0:
            if _lint_skipped_message(out):
                parts.append("(lint skipped — ruff not installed; run: pip install ruff)")
            else:
                all_ok = False

    test_cmd = _resolve_test_command(workspace, profile)
    if test_cmd:
        code, out = _run_command_raw(workspace, test_cmd)
        parts.append(f"=== tests ===\n{out}")
        if code != 0:
            all_ok = False
    elif not lint_cmd:
        parts.append("No verify_command or lint_command configured.")

    summary = "VERIFY_OK" if all_ok else "VERIFY_FAILED"
    return all_ok, f"{summary}\n\n" + "\n\n".join(parts)


def _load_project_instructions(workspace: Path) -> str:
    chunks: list[str] = []
    for name in ("AGENTS.md", "agents.md", ".cursorrules", "CONTRIBUTING.md"):
        p = workspace / name
        if p.is_file():
            try:
                chunks.append(p.read_text(encoding="utf-8")[:5000])
            except Exception as e:
                logger.warning("Failed to read project instructions %s: %s", name, e)
    si = workspace / "memory" / "self_improvements.md"
    if si.is_file():
        try:
            chunks.append(si.read_text(encoding="utf-8")[:4000])
        except Exception as e:
            logger.warning("Failed to read self_improvements.md: %s", e)
    return "\n\n---\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _is_rate_limit_error(e: Exception) -> bool:
    low = str(e).lower()
    return "429" in low or "quota" in low or "resource_exhausted" in low


def _agent_system_prompt() -> str:
    return """You are a coding agent in one project workspace.

Respond with exactly ONE JSON object per turn — no markdown outside JSON.

Actions:
- {"action":"grep","pattern":"text","glob":"*.py"}
- {"action":"read","path":"path.py","start_line":1,"end_line":60}
- {"action":"patch","path":"path.py","diff":"@@ -1,3 +1,4 @@\\n ..."} 
- {"action":"patch","path":"path.py","search":"old","replace":"new"}  (only if diff is awkward)
- {"action":"patch_lines","path":"path.py","start_line":10,"end_line":12,"content":"new lines"}
- {"action":"list_dir","path":".","depth":2}
- {"action":"run"}  — lint+tests from profile (or {"action":"run","command":"git status"})
- {"action":"finish","message":"..."}

Rules:
1. Read AGENTS.md conventions; grep/read before editing.
2. CRITICAL: You MUST read the exact lines of the target file immediately before patching to get the exact indentation and line breaks correct. Patching blind leads to "Patch failed: context mismatch" errors!
3. Prefer unified diff in "diff" (with @@ hunks). Include 2–3 context lines per hunk.
4. After each patch, lint+tests run automatically. If VERIFY_OK, call finish immediately.
5. Minimal changes only. Never touch api_keys or secrets.
6. If VERIFY_FAILED, read the error lines, grep if needed, patch again.
7. Do not invent paths — use the cached file tree."""



def _parse_agent_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        logger.debug("Direct JSON parse failed, trying regex extraction")
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            logger.debug("Regex-extracted JSON also failed to parse")
            return None
    return None


def _post_patch_result(workspace: Path, profile: dict, patch_msg: str) -> str:
    if "Patch rejected" in patch_msg:
        return patch_msg
    if "Patched" not in patch_msg and "patched" not in patch_msg.lower():
        return patch_msg
    invalidate_tree_cache(workspace)
    ok, verify_out = _run_verify(workspace, profile)
    combined = f"{patch_msg}\n\n--- verify ---\n{verify_out}"
    if ok:
        return f"FINISH: All checks passed after patch.\n{combined}"
    return combined


def _execute_agent_action(workspace: Path, data: dict, profile: dict) -> str:
    action = (data.get("action") or "").lower().strip()

    if action == "grep":
        return _grep(workspace, data.get("pattern", ""), data.get("glob", ""))

    if action == "read":
        return _read_file(
            workspace,
            data.get("path", ""),
            int(data.get("start_line", 1)),
            int(data["end_line"]) if data.get("end_line") else None,
        )

    if action == "patch":
        msg = _apply_patch(
            workspace,
            data.get("path", ""),
            data.get("search", ""),
            data.get("replace", ""),
            data.get("diff", ""),
        )
        return _post_patch_result(workspace, profile, msg)

    if action == "patch_lines":
        msg = _apply_patch_lines(
            workspace,
            data.get("path", ""),
            int(data.get("start_line", 1)),
            int(data.get("end_line", data.get("start_line", 1))),
            data.get("content", ""),
        )
        return _post_patch_result(workspace, profile, msg)

    if action == "list_dir":
        return _list_dir(workspace, data.get("path", "."), int(data.get("depth", 2)))

    if action == "run":
        cmd = (data.get("command") or "").strip()
        t = int(data.get("timeout", 30))
        if cmd:
            code, out = _run_command_raw(workspace, cmd, timeout=t)
            tag = "OK" if code == 0 else f"FAILED (exit {code})"
            return f"{tag}\n\n{out}"
        ok, out = _run_verify(workspace, profile)
        if ok:
            return f"FINISH: {out}"
        return out

    if action == "finish":
        return f"FINISH: {data.get('message', 'Done.')}"

    return f"Unknown action '{action}'."


def _quick_apply_simple_test_goal(goal: str, workspace: Path) -> tuple[bool, str]:
    """
    Best-effort single-pass local edit for common 'add a test that asserts X' goals.
    This avoids multiple LLM steps (quota-friendly).
    """
    g = (goal or "").strip()
    m = re.search(
        r"(?:in\s+)?([\w./-]*tests/[\w./-]+\.py|[\w./-]+\.py)",
        g,
        re.IGNORECASE,
    )
    if not m:
        return False, ""
    rel = m.group(1).strip().lstrip("/")
    path = _safe_path(workspace, rel)
    if not path.is_file():
        return False, ""

    tm = re.search(r"named\s+(test_\w+)|\b(test_\w+)\b", g, re.IGNORECASE)
    if not tm:
        return False, ""
    test_name = tm.group(1) or tm.group(2)

    assertion = ""
    for pat in (
        r"asserts?\s+`([^`]+)`",
        r'asserts?\s+(.+?)(?:\.\s|$)',
        r"asserts?\s+(\S.+\S)",
    ):
        am = re.search(pat, g, re.IGNORECASE)
        if am:
            assertion = am.group(1).strip().rstrip(".")
            break
    if not assertion:
        return False, ""

    content = path.read_text(encoding="utf-8", errors="replace")
    if f"def {test_name}(" in content:
        return False, ""

    block = (
        "\n\n\n"
        f"def {test_name}():\n"
        f"    assert {assertion}\n"
    )
    path.write_text(content.rstrip() + block, encoding="utf-8")
    return True, f"Added {test_name} to {rel}."


def _pin_workspace(workspace: Path) -> None:
    try:
        from memory import session_brief

        session_brief.pin_coding_workspace(str(workspace))
    except Exception as e:
        logger.debug("Failed to pin workspace: %s", e)


def _planner_user_prompt(
    goal: str,
    workspace: Path,
    instructions: str,
    tree_preview: str,
    profile: dict,
) -> str:
    lint = profile.get("lint_command", "")
    if _lint_skipped(profile):
        lint = "(skipped — tests_only)"
    verify = profile.get("verify_command", "")
    return f"""Workspace: {workspace}
Lint: {lint or '(none)'}
Tests: {verify or '(none)'}
Goal: {goal}

Project instructions:
{instructions or '(none)'}

Cached file tree:
{tree_preview}

Output ONE JSON object only:
{{"steps": [{{"action": "grep", "pattern": "..."}}, ...]}}
Max 5 steps. Allowed: grep, read, patch, patch_lines, list_dir — not run/finish.
Read before patch. Patches use unified diff with @@ hunks."""


def _extract_plan_steps(data: dict | None) -> list[dict]:
    if not data:
        return []
    steps = data.get("steps") or data.get("plan")
    if not isinstance(steps, list):
        return []
    out: list[dict] = []
    for step in steps:
        if isinstance(step, dict) and (step.get("action") or "").strip():
            out.append(step)
    return out


def _execute_plan_steps(
    workspace: Path,
    steps: list[dict],
    profile: dict,
    *,
    limit: int,
) -> tuple[bool, str]:
    history: list[str] = []
    finished = False
    for i, step in enumerate(steps[:limit]):
        action = (step.get("action") or "").lower().strip()
        if action in ("run", "finish"):
            continue
        result = _execute_agent_action(workspace, step, profile)
        history.append(f"Step {i + 1} [{action}]:\n{result[:5000]}")
        if result.startswith("FINISH:"):
            finished = True
            break
    return finished, "\n\n".join(history)


def _gemini_generate(prompt: str) -> str:
    model = get_coding_model()
    system = _agent_system_prompt()
    try:
        return generate_routed(model, prompt, system_instruction=system)
    except Exception as e:
        if _is_rate_limit_error(e):
            time.sleep(RATE_LIMIT_WAIT_SEC)
            return generate_routed(model, prompt, system_instruction=system)
        raise


def _run_one_shot_task(
    goal: str,
    workspace: Path,
    profile: dict,
    instructions: str,
    tree_preview: str,
    speak=None,
    log=None,
    generate_fn=None,
) -> str | None:
    """
    One Lite call → execute plan locally → optional repair call.
    Returns None to fall back to step-by-step loop.
    """
    prompt = _planner_user_prompt(goal, workspace, instructions, tree_preview, profile)
    generate = generate_fn or _gemini_generate

    try:
        raw = generate(prompt)
    except Exception as e:
        if log:
            log(f"One-shot plan failed: {e}")
        return None

    steps = _extract_plan_steps(_parse_agent_json(raw))
    if not steps:
        if log:
            log("One-shot: no plan steps — using step loop")
        return None

    if log:
        log(f"One-shot plan: {len(steps)} step(s)")

    finished, history = _execute_plan_steps(
        workspace, steps, profile, limit=MAX_ONE_SHOT_PLAN_STEPS
    )
    if finished:
        msg = history.split("FINISH:", 1)[-1].strip() if "FINISH:" in history else history
        if speak and len(msg) > 20:
            speak(msg[:200])
        return f"Task completed (one-shot plan).\n{history[-4000:]}"

    ok, verify_out = _run_verify(workspace, profile)
    if ok:
        return f"Task completed (one-shot plan).\n{history}\n\n--- verify ---\n{verify_out}"

    repair_prompt = (
        f"{prompt}\n\nPrevious execution:\n{history[:6000]}\n\n"
        f"Verify result:\n{verify_out[:3000]}\n\n"
        f"Return a SHORT fix plan JSON (max {MAX_REPAIR_PLAN_STEPS} steps) only."
    )
    try:
        raw_repair = generate(repair_prompt)
    except Exception as e:
        logger.warning("One-shot repair generation failed: %s", e)
        return None

    repair_steps = _extract_plan_steps(_parse_agent_json(raw_repair))
    if not repair_steps:
        return None

    if log:
        log(f"One-shot repair: {len(repair_steps)} step(s)")

    finished2, history2 = _execute_plan_steps(
        workspace, repair_steps, profile, limit=MAX_REPAIR_PLAN_STEPS
    )
    combined = f"{history}\n\n--- repair ---\n{history2}"
    if finished2:
        return f"Task completed (one-shot + repair).\n{combined[-6000:]}"

    ok2, verify2 = _run_verify(workspace, profile)
    if ok2:
        return f"Task completed (one-shot + repair).\n{combined}\n\n--- verify ---\n{verify2}"

    return None




# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _get_status(workspace: Path, profile: dict) -> str:
    lint_cmd = profile.get("lint_command", "")
    verify_cmd = profile.get("verify_command", "")
    tree_text = _get_cached_tree(workspace, depth=2, refresh=False)
    tree_lines = len([ln for ln in tree_text.splitlines() if ln.strip()])

    mode = profile.get("verify_mode", "tests_and_lint")
    tests_only = profile.get("tests_only", False)
    return (
        f"workspace_path: {workspace}\n"
        f"lint_command: {lint_cmd}\n"
        f"verify_command: {verify_cmd}\n"
        f"verify_mode: {mode}\n"
        f"tests_only: {tests_only}\n"
        f"coding_model: {profile.get('coding_model', get_coding_model())}\n"
        f"cached_tree_lines: {tree_lines}"
    )


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------

def coding_workspace(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    p = parameters or {}
    action = (p.get("action") or "status").lower().strip()

    try:
        workspace = _resolve_workspace(p.get("workspace_path", "").strip())
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        return str(e)

    profile = _load_profile()

    if action == "set_workspace":
        prof = _load_profile()
        prof["workspace_root"] = str(workspace)
        inferred = _infer_project_profile(workspace)
        prof.update(inferred)
        if p.get("verify_command"):
            prof["verify_command"] = p["verify_command"].strip()
        if p.get("lint_command"):
            prof["lint_command"] = p["lint_command"].strip()
        if p.get("coding_model"):
            prof["coding_model"] = p["coding_model"].strip()
        if "tests_only" in p:
            prof["tests_only"] = bool(p["tests_only"])
        if p.get("verify_mode"):
            prof["verify_mode"] = p["verify_mode"].strip().lower()
        _save_profile(prof)
        invalidate_tree_cache(workspace)
        _pin_workspace(workspace)
        kind = prof.get("project_kind", _project_kind(workspace))
        return (
            f"Workspace set to {workspace}\n"
            f"project: {kind}\n"
            f"lint: {prof.get('lint_command', '') or '(none)'}\n"
            f"tests: {prof.get('verify_command', '') or '(none)'}\n"
            f"verify_mode: {prof.get('verify_mode', 'tests_and_lint')}\n"
            f"tests_only: {prof.get('tests_only', False)}\n"
            f"coding model: {prof.get('coding_model', get_coding_model())}\n"
            f"Tip: run with command= for one-off shell (git, cargo, lumina)."
        )

    if action == "get_profile":
        return json.dumps(_load_profile(), indent=2)

    if action == "status":
        return _get_status(workspace, profile)

    if action == "list_dir":
        return _list_dir(workspace, p.get("path", "."), int(p.get("depth", 2)))

    if action == "grep":
        return _grep(workspace, p.get("pattern", ""), p.get("glob", ""))

    if action == "read":
        return _read_file(
            workspace,
            p.get("path", ""),
            int(p.get("start_line", 1)),
            int(p["end_line"]) if p.get("end_line") else None,
        )

    if action == "patch":
        msg = _apply_patch(
            workspace,
            p.get("path", ""),
            p.get("search", ""),
            p.get("replace", ""),
            p.get("diff", ""),
        )
        return _post_patch_result(workspace, profile, msg)

    if action == "patch_lines":
        msg = _apply_patch_lines(
            workspace,
            p.get("path", ""),
            int(p.get("start_line", 1)),
            int(p.get("end_line", p.get("start_line", 1))),
            p.get("content", ""),
        )
        return _post_patch_result(workspace, profile, msg)

    if action == "run":
        cmd = p.get("command", "").strip()
        t = int(p.get("timeout", 30))
        if cmd:
            code, out = _run_command_raw(workspace, cmd, timeout=t)
            tag = "OK" if code == 0 else f"FAILED (exit {code})"
            return f"{tag}\n\n{out}"
        ok, out = _run_verify(workspace, profile)
        return f"FINISH: {out}" if ok else out

    return (
        "Unknown action. Use set_workspace, get_profile, status, "
        "list_dir, grep, read, patch, patch_lines, or run."
    )
