"""GNOME Shell extension management via gnome-extensions CLI."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_gnome_extensions(args: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a gnome-extensions command and return (ok, stdout, stderr)."""
    cmd = ["gnome-extensions", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "gnome-extensions not found — is GNOME Shell installed?"
    except subprocess.TimeoutExpired:
        return False, "", f"gnome-extensions timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"gnome-extensions error: {e}"


def list_extensions() -> str:
    """List all enabled GNOME Shell extensions."""
    ok, stdout, stderr = _run_gnome_extensions(["list", "--enabled"])
    if not ok:
        return f"Failed to list extensions: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No enabled GNOME extensions found."

    result = [f"Enabled extensions ({len(lines)}):"]
    for i, ext in enumerate(lines, 1):
        ext_clean = ext.strip()
        if ext_clean:
            result.append(f"  {i}. {ext_clean}")
    return "\n".join(result)


def list_all_extensions() -> str:
    """List all GNOME Shell extensions (enabled and disabled)."""
    ok, stdout, stderr = _run_gnome_extensions(["list"])
    if not ok:
        return f"Failed to list extensions: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No GNOME extensions found."

    result = [f"All extensions ({len(lines)}):"]
    for i, ext in enumerate(lines, 1):
        ext_clean = ext.strip()
        if ext_clean:
            result.append(f"  {i}. {ext_clean}")
    return "\n".join(result)


def enable_extension(uuid: str) -> str:
    """Enable a GNOME Shell extension by UUID."""
    ext_id = uuid.strip()
    if not ext_id:
        return "Provide an extension UUID."

    ok, _, stderr = _run_gnome_extensions(["enable", ext_id])
    if ok:
        # Also try to enable via gnome-shell-extension-tool as fallback
        try:
            subprocess.run(
                ["gnome-shell-extension-tool", "-e", ext_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return f"Extension '{ext_id}' enabled."
    if "not found" in (stderr or "").lower():
        return f"Extension '{ext_id}' not found. Use list_all_extensions to see available UUIDs."
    return f"Failed to enable extension '{ext_id}': {stderr}"


def disable_extension(uuid: str) -> str:
    """Disable a GNOME Shell extension by UUID."""
    ext_id = uuid.strip()
    if not ext_id:
        return "Provide an extension UUID."

    ok, _, stderr = _run_gnome_extensions(["disable", ext_id])
    if ok:
        return f"Extension '{ext_id}' disabled."
    if "not found" in (stderr or "").lower():
        return f"Extension '{ext_id}' not found."
    return f"Failed to disable extension '{ext_id}': {stderr}"


def extension_info(uuid: str) -> str:
    """Show info about a GNOME Shell extension."""
    ext_id = uuid.strip()
    if not ext_id:
        return "Provide an extension UUID."

    ok, stdout, stderr = _run_gnome_extensions(["info", ext_id])
    if ok:
        return f"Extension info for '{ext_id}':\n{stdout[:2000]}"
    if "not found" in (stderr or "").lower():
        return f"Extension '{ext_id}' not found."
    return f"Failed to get info for '{ext_id}': {stderr or stdout[:200]}"
