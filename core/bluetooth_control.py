"""Bluetooth device management via bluetoothctl."""

from __future__ import annotations

import subprocess
import time

from core.logger import get_logger

logger = get_logger(__name__)


def _run_bluetoothctl(args: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a bluetoothctl command and return (ok, stdout, stderr)."""
    cmd = ["bluetoothctl", *args]
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
        return False, "", "bluetoothctl not found — install bluez-utils."
    except subprocess.TimeoutExpired:
        return False, "", f"bluetoothctl timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"bluetoothctl error: {e}"


def list_paired_devices() -> str:
    """List all paired Bluetooth devices."""
    ok, stdout, stderr = _run_bluetoothctl(["paired-devices"])
    if not ok:
        return f"Failed to list paired devices: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No paired Bluetooth devices found."

    result = [f"Paired devices ({len(lines)}):"]
    for line in lines:
        parts = line.strip().split(None, 2)
        if len(parts) >= 3:
            result.append(f"  {parts[1]}  {parts[2]}")
        elif len(parts) >= 2:
            result.append(f"  {parts[1]}")
    return "\n".join(result)


def scan_devices(timeout: int = 5) -> str:
    """Scan for Bluetooth devices for a given number of seconds."""
    scan_time = max(2, min(30, int(timeout)))

    # Start scanning in background
    ok, _, stderr = _run_bluetoothctl(["scan", "on"], timeout=scan_time + 2)
    if not ok and "not powered" in stderr.lower():
        return "Bluetooth is not powered on. Turn on Bluetooth first."

    # Small wait for discovery
    time.sleep(scan_time)

    # Now list discovered devices
    ok, stdout, stderr = _run_bluetoothctl(["devices"])
    if not ok:
        return f"Failed to scan: {stderr or stdout}"

    # Turn off scanning
    _run_bluetoothctl(["scan", "off"], timeout=5)

    lines = stdout.splitlines()
    if not lines:
        return f"No Bluetooth devices found after {scan_time}s scan."

    result = [f"Devices found ({len(lines)}):"]
    for line in lines:
        parts = line.strip().split(None, 2)
        if len(parts) >= 3:
            result.append(f"  {parts[1]}  {parts[2]}")
    return "\n".join(result)


def connect_device(mac: str) -> str:
    """Connect to a Bluetooth device by MAC address."""
    addr = mac.strip()
    if not addr:
        return "Provide a Bluetooth MAC address (XX:XX:XX:XX:XX:XX)."

    ok, stdout, stderr = _run_bluetoothctl(["connect", addr], timeout=20)
    if ok:
        return f"Connected to {addr}."
    if "not available" in (stderr or stdout).lower():
        return f"Device {addr} not found or not available."
    if "not powered" in (stderr or stdout).lower():
        return "Bluetooth is not powered on. Turn on Bluetooth first."
    return f"Failed to connect to {addr}: {stderr or stdout[:200]}"


def disconnect_device(mac: str) -> str:
    """Disconnect a Bluetooth device by MAC address."""
    addr = mac.strip()
    if not addr:
        return "Provide a Bluetooth MAC address (XX:XX:XX:XX:XX:XX)."

    ok, _, stderr = _run_bluetoothctl(["disconnect", addr], timeout=10)
    if ok:
        return f"Disconnected from {addr}."
    return f"Failed to disconnect {addr}: {stderr}"


def bluetooth_on() -> str:
    """Power on the Bluetooth adapter."""
    ok, _, stderr = _run_bluetoothctl(["power", "on"])
    if ok:
        return "Bluetooth powered on."

    # Try rfkill as fallback
    try:
        subprocess.run(
            ["rfkill", "unblock", "bluetooth"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ok, _, stderr = _run_bluetoothctl(["power", "on"])
        if ok:
            return "Bluetooth powered on."
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass

    return f"Failed to power on Bluetooth: {stderr}"


def bluetooth_off() -> str:
    """Power off the Bluetooth adapter."""
    ok, _, stderr = _run_bluetoothctl(["power", "off"])
    if ok:
        return "Bluetooth powered off."
    return f"Failed to power off Bluetooth: {stderr}"


def device_info(mac: str) -> str:
    """Show detailed info about a Bluetooth device."""
    addr = mac.strip()
    if not addr:
        return "Provide a Bluetooth MAC address (XX:XX:XX:XX:XX:XX)."

    ok, stdout, stderr = _run_bluetoothctl(["info", addr])
    if ok:
        return f"Device info for {addr}:\n{stdout[:2000]}"
    return f"Failed to get info for {addr}: {stderr or stdout[:200]}"
