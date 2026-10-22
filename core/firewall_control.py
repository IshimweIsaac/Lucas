"""Firewall management via firewall-cmd (firewalld)."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_firewall_cmd(args: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a firewall-cmd command and return (ok, stdout, stderr)."""
    cmd = ["firewall-cmd", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "firewall-cmd not found — install firewalld."
    except subprocess.TimeoutExpired:
        return False, "", f"firewall-cmd timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"firewall-cmd error: {e}"


def list_zones() -> str:
    """List all firewall zones and their configurations."""
    ok, stdout, stderr = _run_firewall_cmd(["--list-all-zones"])
    if not ok:
        return f"Failed to list zones: {stderr or stdout}"
    if not stdout:
        return "No firewall zones found."
    return stdout[:3000]


def list_open_ports() -> str:
    """List all open ports in the firewall."""
    ok, stdout, stderr = _run_firewall_cmd(["--list-ports"])
    if not ok:
        return f"Failed to list ports: {stderr or stdout}"
    if not stdout or stdout == "":
        return "No ports are explicitly open (services may still be allowed)."
    return f"Open ports:\n{stdout}"


def list_services() -> str:
    """List allowed services through the firewall."""
    ok, stdout, stderr = _run_firewall_cmd(["--list-services"])
    if not ok:
        return f"Failed to list services: {stderr or stdout}"
    if not stdout:
        return "No services are configured."
    return f"Allowed services: {stdout}"


def add_port(port: str, protocol: str = "tcp", zone: str = "public") -> str:
    """Add a port to the firewall (permanent change, then reload)."""
    port_clean = port.strip()
    if not port_clean:
        return "Provide a port number."
    if not port_clean.isdigit():
        return f"Invalid port: '{port}'. Must be a number."

    proto = protocol.strip().lower()
    if proto not in ("tcp", "udp"):
        return "Protocol must be 'tcp' or 'udp'."

    zone_clean = zone.strip().lower()
    port_spec = f"{port_clean}/{proto}"

    ok, _, stderr = _run_firewall_cmd(
        ["--permanent", "--zone=" + zone_clean, "--add-port=" + port_spec],
    )
    if not ok:
        if "already" in stderr.lower():
            # Already added, just reload
            _run_firewall_cmd(["--reload"])
            return f"Port {port_spec} was already open in zone '{zone_clean}'."
        return f"Failed to add port {port_spec}: {stderr}"

    # Reload to apply
    reload_ok, _, reload_err = _run_firewall_cmd(["--reload"])
    if not reload_ok:
        return f"Port added but reload failed: {reload_err}"

    return f"Port {port_spec} opened in zone '{zone_clean}' (permanent)."


def remove_port(port: str, protocol: str = "tcp", zone: str = "public") -> str:
    """Remove a port from the firewall (permanent change, then reload)."""
    port_clean = port.strip()
    if not port_clean:
        return "Provide a port number."
    if not port_clean.isdigit():
        return f"Invalid port: '{port}'. Must be a number."

    proto = protocol.strip().lower()
    if proto not in ("tcp", "udp"):
        return "Protocol must be 'tcp' or 'udp'."

    zone_clean = zone.strip().lower()
    port_spec = f"{port_clean}/{proto}"

    ok, _, stderr = _run_firewall_cmd(
        ["--permanent", "--zone=" + zone_clean, "--remove-port=" + port_spec],
    )
    if not ok:
        if "not" in stderr.lower() and "enabled" in stderr.lower():
            return f"Port {port_spec} was not open in zone '{zone_clean}'."
        return f"Failed to remove port {port_spec}: {stderr}"

    reload_ok, _, reload_err = _run_firewall_cmd(["--reload"])
    if not reload_ok:
        return f"Port removed but reload failed: {reload_err}"

    return f"Port {port_spec} removed from zone '{zone_clean}' (permanent)."


def firewall_status() -> str:
    """Check if firewalld is running."""
    ok, stdout, stderr = _run_firewall_cmd(["--state"])
    if ok:
        return f"Firewall status: {stdout}"
    return f"Firewall is not running: {stderr or stdout}"
