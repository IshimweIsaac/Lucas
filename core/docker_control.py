"""Docker container management for Lucas."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def list_containers(all_containers: bool = False) -> str:
    """List running Docker containers."""
    try:
        cmd = [
            "docker", "ps", "--format",
            "table {{.Names}}\t{{.Status}}\t{{.Ports}}",
        ]
        if all_containers:
            cmd.insert(2, "-a")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return "No containers running."
    except FileNotFoundError:
        return "Docker not found."
    except Exception as exc:
        return f"Failed to list containers: {exc}"


def container_status(container_name: str) -> str:
    """Get status of a specific container."""
    try:
        r = subprocess.run(
            [
                "docker", "ps", "-a", "--filter", f"name={container_name}",
                "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return f"No container found: {container_name}"
    except Exception as exc:
        return f"Failed: {exc}"


def start_container(container_name: str) -> str:
    """Start a Docker container."""
    try:
        r = subprocess.run(
            ["docker", "start", container_name],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return f"Container started: {container_name}"
        return f"Failed to start {container_name}: {r.stderr.strip()[:200]}"
    except Exception as exc:
        return f"Failed: {exc}"


def stop_container(container_name: str) -> str:
    """Stop a Docker container."""
    try:
        r = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return f"Container stopped: {container_name}"
        return f"Failed to stop {container_name}: {r.stderr.strip()[:200]}"
    except Exception as exc:
        return f"Failed: {exc}"


def restart_container(container_name: str) -> str:
    """Restart a Docker container."""
    try:
        r = subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return f"Container restarted: {container_name}"
        return f"Failed to restart {container_name}: {r.stderr.strip()[:200]}"
    except Exception as exc:
        return f"Failed: {exc}"


def list_images() -> str:
    """List Docker images."""
    try:
        r = subprocess.run(
            [
                "docker", "images", "--format",
                "table {{.Repository}}\t{{.Tag}}\t{{.Size}}",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return "No images found."
    except Exception as exc:
        return f"Failed: {exc}"


def docker_info() -> str:
    """Get Docker system info."""
    try:
        r = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            version = r.stdout.strip()
            ps = subprocess.run(
                ["docker", "ps", "-q"], capture_output=True, text=True, timeout=10,
            )
            count = len(ps.stdout.strip().splitlines()) if ps.stdout.strip() else 0
            return f"Docker {version} — {count} container(s) running"
        return "Docker not running."
    except FileNotFoundError:
        return "Docker not found."
    except Exception as exc:
        return f"Failed: {exc}"
