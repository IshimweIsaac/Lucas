"""Disk and storage management — list, mount, unmount, eject via lsblk/udisksctl."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_lsblk(args: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run an lsblk command and return (ok, stdout, stderr)."""
    cmd = ["lsblk", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "lsblk not found — install util-linux."
    except subprocess.TimeoutExpired:
        return False, "", f"lsblk timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"lsblk error: {e}"


def _run_udisksctl(args: list[str], timeout: int = 15) -> tuple[bool, str, str]:
    """Run a udisksctl command and return (ok, stdout, stderr)."""
    cmd = ["udisksctl", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "udisksctl not found — install udisks2."
    except subprocess.TimeoutExpired:
        return False, "", f"udisksctl timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"udisksctl error: {e}"


def list_disks() -> str:
    """List all block devices with size, type, mountpoint, label, model."""
    ok, stdout, stderr = _run_lsblk(["-o", "NAME,SIZE,TYPE,MOUNTPOINT,LABEL,MODEL"])
    if not ok:
        return f"Failed to list disks: {stderr or stdout}"
    if not stdout:
        return "No block devices found."
    return stdout


def disk_usage() -> str:
    """Show disk usage via df -h."""
    try:
        result = subprocess.run(
            ["df", "-h"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        err = result.stderr.strip() or result.stdout.strip()
        return f"Failed to get disk usage: {err}"
    except FileNotFoundError:
        return "df not found."
    except subprocess.TimeoutExpired:
        return "df command timed out."
    except Exception as e:
        return f"df error: {e}"


def _normalize_device(device: str) -> str:
    """Normalize a device path to /dev/ form."""
    dev = device.strip()
    if not dev:
        return ""
    if dev.startswith("/dev/"):
        return dev
    return f"/dev/{dev}"


def mount_device(device: str) -> str:
    """Mount a block device by name (e.g. sda1 or /dev/sda1)."""
    dev_path = _normalize_device(device)
    if not dev_path:
        return "Provide a device name (e.g. sda1 or /dev/sda1)."

    ok, stdout, stderr = _run_udisksctl(["mount", "-b", dev_path])
    if ok:
        # Parse mount point from output like "Mounted at /run/media/..."
        if "mounted at" in stdout.lower():
            parts = stdout.split("at", 1)
            if len(parts) > 1:
                return f"Mounted {dev_path} at{parts[1]}"
        return f"Mounted {dev_path}."
    if "already mounted" in (stderr or "").lower():
        return f"{dev_path} is already mounted."
    if "not found" in (stderr or "").lower():
        return f"Device {dev_path} not found."
    return f"Failed to mount {dev_path}: {stderr or stdout}"


def unmount_device(device: str) -> str:
    """Unmount a block device by name (e.g. sda1 or /dev/sda1)."""
    dev_path = _normalize_device(device)
    if not dev_path:
        return "Provide a device name (e.g. sda1 or /dev/sda1)."

    ok, stdout, stderr = _run_udisksctl(["unmount", "-b", dev_path])
    if ok:
        return f"Unmounted {dev_path}."
    if "not mounted" in (stderr or "").lower():
        return f"{dev_path} is not mounted."
    return f"Failed to unmount {dev_path}: {stderr or stdout}"


def safely_eject(device: str) -> str:
    """Safely power off a block device (for USB drives)."""
    dev_path = _normalize_device(device)
    if not dev_path:
        return "Provide a device name (e.g. sda or /dev/sda)."

    ok, stdout, stderr = _run_udisksctl(["power-off", "-b", dev_path])
    if ok:
        return f"Device {dev_path} safely ejected."
    return f"Failed to eject {dev_path}: {stderr or stdout}"


def disk_info(device: str) -> str:
    """Show detailed info about a specific device including FSTYPE and UUID."""
    dev_path = _normalize_device(device)
    if not dev_path:
        return "Provide a device name (e.g. sda1 or /dev/sda1)."

    ok, stdout, stderr = _run_lsblk(
        ["-o", "NAME,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINT", dev_path]
    )
    if not ok:
        return f"Failed to get info for {dev_path}: {stderr or stdout}"
    if not stdout:
        return f"No info available for {dev_path}."
    return stdout
