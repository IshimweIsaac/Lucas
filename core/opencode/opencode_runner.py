"""CLI wrapper for OpenCode (non-HTTP commands)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_BIN = Path.home() / ".opencode" / "bin" / "opencode"


def find_opencode() -> str | None:
    """Locate the ``opencode`` executable."""
    found = shutil.which("opencode")
    if found:
        return found
    if _DEFAULT_BIN.is_file():
        return str(_DEFAULT_BIN)
    return None


def opencode_available() -> bool:
    return find_opencode() is not None


def run_opencode(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run ``opencode`` with argument list (no shell)."""
    bin_path = find_opencode()
    if not bin_path:
        return 1, (
            "OpenCode not found. Install: curl -fsSL https://opencode.ai/install | bash"
        )

    cmd = [bin_path, *args]
    work = Path(cwd).expanduser().resolve() if cwd else None
    if work and not work.is_dir():
        return 1, f"Workspace not found: {work}"

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work) if work else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        return 1, f"opencode timed out after {timeout}s"
    except OSError as exc:
        logger.warning("[opencode_runner] run failed: %s", exc)
        return 1, f"Failed to run opencode: {exc}"

    out = ((proc.stdout or "") + (proc.stderr or "")).strip() or "(no output)"
    return proc.returncode, out


def run_opencode_shell(
    command: str,
    *,
    cwd: str | Path | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    """Run a shell pipeline via ``opencode``'s underlying shell when needed."""
    if not command or not command.strip():
        return 1, "No command provided."
    use_shell = any(tok in command for tok in ("|", "&&", "||", ";", ">", "<"))
    if use_shell:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(Path(cwd).expanduser()) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return 1, f"Command timed out after {timeout}s"
        out = ((proc.stdout or "") + (proc.stderr or "")).strip() or "(no output)"
        return proc.returncode, out

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    bin_path = find_opencode()
    if parts and parts[0] == "opencode" and bin_path:
        parts[0] = bin_path
    try:
        proc = subprocess.run(
            parts,
            cwd=str(Path(cwd).expanduser()) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, f"Command timed out after {timeout}s"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip() or "(no output)"
    return proc.returncode, out


def format_cli_result(code: int, out: str, *, action: str = "") -> str:
    tag = "OK" if code == 0 else f"ERROR (exit {code})"
    prefix = f"[{action}] " if action else ""
    return f"{prefix}{tag}\n\n{out}".strip()
