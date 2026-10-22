"""Systemd service management — list, start, stop, enable, disable services."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)

_USER_SERVICE_PREFIX = ["systemctl", "--user"]
_SYSTEM_SERVICE_PREFIX = ["systemctl"]


def _run_systemctl(
    args: list[str], timeout: int = 15, use_user: bool = True
) -> tuple[bool, str, str]:
    """Run a systemctl command, trying user mode first then system mode.

    Returns (ok, stdout, stderr).
    """
    if use_user:
        cmd = _USER_SERVICE_PREFIX + args
    else:
        cmd = _SYSTEM_SERVICE_PREFIX + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        return result.returncode == 0, stdout, stderr
    except FileNotFoundError:
        return False, "", "systemctl not found — is systemd installed?"
    except subprocess.TimeoutExpired:
        return False, "", f"systemctl timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"systemctl error: {e}"


def _format_service_list(lines: str) -> str:
    """Format systemctl list-units output into a readable list."""
    result = []
    for line in lines.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT") or "●" in line and "loaded" not in line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            name = parts[0]
            load = parts[1]
            active = parts[2]
            sub = parts[3] if len(parts) > 3 else ""
            result.append(f"  {name:<45} {load:<8} {active:<10} {sub}")
    return "\n".join(result)


def list_services(filter_str: str = "") -> str:
    """List systemd services, optionally filtered."""
    args = ["list-units", "--type=service", "--all", "--no-pager"]
    ok, stdout, stderr = _run_systemctl(args, use_user=True)
    if ok:
        output = stdout
    else:
        ok, stdout, stderr = _run_systemctl(args, use_user=False)
        if not ok:
            return f"Failed to list services: {stderr or stdout}"
        output = stdout

    if filter_str:
        lines = [
            line for line in output.splitlines() if filter_str.lower() in line.lower()
        ]
        output = "\n".join(lines)

    formatted = _format_service_list(output)
    if not formatted:
        return "No services found."

    lines_list = formatted.splitlines()
    return f"Services ({len(lines_list)}):\n{formatted}"


def service_status(service_name: str) -> str:
    """Show status of a specific service."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    # Try user service first
    ok, stdout, stderr = _run_systemctl(
        ["status", name, "--no-pager", "--lines=20"], use_user=True
    )
    if ok:
        return f"Service '{name}' status (user):\n{stdout[:2000]}"

    # Try system service
    ok, stdout, stderr = _run_systemctl(
        ["status", name, "--no-pager", "--lines=20"], use_user=False
    )
    if ok:
        return f"Service '{name}' status:\n{stdout[:2000]}"

    err = stderr or stdout
    return f"Service '{name}' not found: {err[:500]}"


def start_service(service_name: str) -> str:
    """Start a service. Tries user mode first, then system with sudo info."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    ok, _, stderr = _run_systemctl(["start", name], use_user=True)
    if ok:
        return f"Service '{name}' started (user)."

    # Try system mode
    ok, _, stderr = _run_systemctl(["start", name], use_user=False)
    if ok:
        return f"Service '{name}' started."
    if "permission denied" in stderr.lower() or "not permitted" in stderr.lower():
        return (
            f"'{name}' is a system service and requires admin privileges. "
            "Say 'yes' to run with sudo: systemctl start " + name
        )
    return f"Failed to start service '{name}': {stderr}"


def stop_service(service_name: str) -> str:
    """Stop a service. Tries user mode first, then system with sudo info."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    ok, _, stderr = _run_systemctl(["stop", name], use_user=True)
    if ok:
        return f"Service '{name}' stopped (user)."

    ok, _, stderr = _run_systemctl(["stop", name], use_user=False)
    if ok:
        return f"Service '{name}' stopped."
    if "permission denied" in stderr.lower() or "not permitted" in stderr.lower():
        return (
            f"'{name}' is a system service and requires admin privileges. "
            "Say 'yes' to run with sudo: systemctl stop " + name
        )
    return f"Failed to stop service '{name}': {stderr}"


def restart_service(service_name: str) -> str:
    """Restart a service. Tries user mode first, then system with sudo info."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    ok, _, stderr = _run_systemctl(["restart", name], use_user=True)
    if ok:
        return f"Service '{name}' restarted (user)."

    ok, _, stderr = _run_systemctl(["restart", name], use_user=False)
    if ok:
        return f"Service '{name}' restarted."
    if "permission denied" in stderr.lower() or "not permitted" in stderr.lower():
        return (
            f"'{name}' is a system service and requires admin privileges. "
            "Say 'yes' to run with sudo: systemctl restart " + name
        )
    return f"Failed to restart service '{name}': {stderr}"


def enable_service(service_name: str) -> str:
    """Enable a service to start at boot. Tries user mode first, then system."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    ok, _, stderr = _run_systemctl(["enable", name], use_user=True)
    if ok:
        return f"Service '{name}' enabled (user)."

    ok, _, stderr = _run_systemctl(["enable", name], use_user=False)
    if ok:
        return f"Service '{name}' enabled."
    if "permission denied" in stderr.lower() or "not permitted" in stderr.lower():
        return (
            f"'{name}' is a system service and requires admin privileges. "
            "Say 'yes' to run with sudo: systemctl enable " + name
        )
    return f"Failed to enable service '{name}': {stderr}"


def disable_service(service_name: str) -> str:
    """Disable a service from starting at boot."""
    name = service_name.strip()
    if not name:
        return "Provide a service name."

    ok, _, stderr = _run_systemctl(["disable", name], use_user=True)
    if ok:
        return f"Service '{name}' disabled (user)."

    ok, _, stderr = _run_systemctl(["disable", name], use_user=False)
    if ok:
        return f"Service '{name}' disabled."
    if "permission denied" in stderr.lower() or "not permitted" in stderr.lower():
        return (
            f"'{name}' is a system service and requires admin privileges. "
            "Say 'yes' to run with sudo: systemctl disable " + name
        )
    return f"Failed to disable service '{name}': {stderr}"
