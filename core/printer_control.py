"""Printer management via CUPS — lpstat, lpq, cancel."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_cups_command(cmd: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a CUPS command and return (ok, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        name = cmd[0]
        return False, "", f"{name} not found — install CUPS (cups-client)."
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"Command error: {e}"


def list_printers() -> str:
    """List all configured printers with status."""
    ok, stdout, stderr = _run_cups_command(
        ["lpstat", "-p", "-d"],
    )
    if not ok:
        return f"Failed to list printers: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No printers configured."

    result = []
    for line in lines:
        line = line.strip()
        if line:
            result.append(f"  {line}")

    return f"Printers ({len(result)}):\n" + "\n".join(result)


def printer_status(printer_name: str) -> str:
    """Show status of a specific printer."""
    name = printer_name.strip()
    if not name:
        return "Provide a printer name."

    ok, stdout, stderr = _run_cups_command(
        ["lpstat", "-p", name],
    )
    if not ok:
        if "unknown" in (stderr or "").lower():
            return f"Printer '{name}' not found."
        return f"Failed to get printer status: {stderr or stdout}"
    return stdout or f"No status info for printer '{name}'."


def list_print_jobs() -> str:
    """List all print jobs in the queue."""
    ok, stdout, stderr = _run_cups_command(
        ["lpq"],
    )
    if not ok:
        return f"Failed to list print jobs: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No print jobs in queue."
    if "no entries" in stdout.lower():
        return "No print jobs in queue."

    return f"Print jobs:\n{stdout}"


def cancel_job(job_id: str) -> str:
    """Cancel a print job by ID."""
    jid = job_id.strip()
    if not jid:
        return "Provide a job ID."

    ok, _, stderr = _run_cups_command(
        ["cancel", jid],
    )
    if ok:
        return f"Print job {jid} cancelled."
    if "not found" in (stderr or "").lower():
        return f"Print job {jid} not found."
    return f"Failed to cancel job {jid}: {stderr}"
