"""Package management via dnf — list, search, install, remove, info."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_dnf(
    args: list[str], timeout: int = 30, needs_sudo: bool = False
) -> tuple[bool, str, str]:
    """Run a dnf command and return (ok, stdout, stderr).

    If *needs_sudo* is False, runs as user (read-only commands).
    If *needs_sudo* is True, runs as user but returns a message about sudo.
    """
    cmd = ["dnf", *args]
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
        return False, "", "dnf not found — is this a Fedora/RHEL system?"
    except subprocess.TimeoutExpired:
        return False, "", f"dnf timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"dnf error: {e}"


def list_installed(filter_str: str = "") -> str:
    """List installed packages, optionally filtered."""
    args = ["list", "installed"]
    ok, stdout, stderr = _run_dnf(args)

    if not ok:
        return f"Failed to list installed packages: {stderr or stdout}"
    if not stdout:
        return "No packages found."

    lines = stdout.splitlines()
    if filter_str:
        lines = [line for line in lines if filter_str.lower() in line.lower()]

    if len(lines) <= 1:
        if filter_str:
            return f"No installed packages matching '{filter_str}'."
        return "No packages found."

    # First line is header
    packages = lines[1:]
    result = [f"Installed packages ({len(packages)}):"]
    for pkg in packages:
        parts = pkg.strip().split()
        if parts:
            result.append(f"  {parts[0]}")
    return "\n".join(result)


def check_updates() -> str:
    """Check for available package updates."""
    ok, stdout, stderr = _run_dnf(["check-update"], timeout=60)

    if ok and not stdout:
        return "System is up to date — no updates available."

    if not ok:
        # dnf check-update returns exit code 100 when updates are available
        if stdout:
            lines = stdout.splitlines()
            if len(lines) <= 1:
                return "No updates available."
            packages = []
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    packages.append(f"  {parts[0]}  {parts[1]}")
            if packages:
                return f"Updates available ({len(packages)}):\n" + "\n".join(packages)
        return f"Failed to check updates: {stderr or stdout}"

    return "No updates available."


def install_package(package: str) -> str:
    """Install a package (requires admin privileges)."""
    pkg = package.strip()
    if not pkg:
        return "Provide a package name to install."

    return (
        f"Installing '{pkg}' requires admin privileges. "
        "Say 'yes' to run with sudo: dnf install -y " + pkg
    )


def remove_package(package: str) -> str:
    """Remove a package (requires admin privileges)."""
    pkg = package.strip()
    if not pkg:
        return "Provide a package name to remove."

    return (
        f"Removing '{pkg}' requires admin privileges. "
        "Say 'yes' to run with sudo: dnf remove -y " + pkg
    )


def package_info(package: str) -> str:
    """Show detailed info about a package."""
    pkg = package.strip()
    if not pkg:
        return "Provide a package name."

    ok, stdout, stderr = _run_dnf(["info", pkg])
    if not ok:
        if (
            "not found" in (stderr or "").lower()
            or "no match" in (stderr or "").lower()
        ):
            return f"Package '{pkg}' not found."
        return f"Failed to get info for '{pkg}': {stderr or stdout}"
    return stdout[:2000] if stdout else f"No info available for '{pkg}'."


def search_packages(query: str) -> str:
    """Search for packages matching a query."""
    q = query.strip()
    if not q:
        return "Provide a search query."

    ok, stdout, stderr = _run_dnf(["search", q], timeout=30)

    if not ok:
        if (
            "no match" in (stderr or "").lower()
            or "no results" in (stderr or "").lower()
        ):
            return f"No packages found matching '{q}'."
        return f"Search failed: {stderr or stdout}"

    lines = stdout.splitlines()
    if len(lines) <= 1:
        return f"No packages found matching '{q}'."

    # Lines are: Name : Summary
    result = [f"Search results for '{q}' ({len(lines) - 1}):"]
    for line in lines[1:]:
        line = line.strip()
        if line:
            result.append(f"  {line}")
    return "\n".join(result)
