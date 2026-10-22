"""WiFi and network control via nmcli (NetworkManager CLI)."""

from __future__ import annotations

import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def _run_nmcli(args: list[str], timeout: int = 15) -> tuple[bool, str, str]:
    """Run an nmcli command and return (ok, stdout, stderr)."""
    cmd = ["nmcli", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        return result.returncode == 0, stdout, stderr
    except FileNotFoundError:
        return False, "", "nmcli not found — is NetworkManager installed?"
    except subprocess.TimeoutExpired:
        return False, "", f"nmcli command timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"nmcli error: {e}"


def scan_wifi() -> str:
    """Scan available WiFi networks and return a formatted listing."""
    ok, stdout, stderr = _run_nmcli(
        ["-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
        timeout=20,
    )
    if not ok:
        if "No network" in stderr or "No available" in stderr:
            return "No WiFi networks found. Is Wi-Fi enabled?"
        return f"WiFi scan failed: {stderr or stdout}"

    lines = stdout.splitlines()
    if len(lines) <= 1:
        return "No WiFi networks found in range."

    networks = []
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.rsplit(None, 2)
        if len(parts) >= 3:
            ssid = parts[0]
            signal = parts[-2]
            security = parts[-1]
        elif len(parts) == 2:
            ssid = parts[0]
            signal = parts[-1]
            security = "Open"
        else:
            ssid = line.strip()
            signal = "?"
            security = "?"

        if ssid and ssid != "--":
            lock = "🔒" if security.lower() not in ("", "--", "open") else "  "
            networks.append(f"  {lock} {ssid:<25} {signal:>4}%  {security}")

    if not networks:
        return "No WiFi networks found."

    lines_out = [
        f"Found {len(networks)} WiFi networks:",
        *networks,
    ]
    return "\n".join(lines_out)


def connect_wifi(ssid: str, password: str = "") -> str:
    """Connect to a WiFi network by SSID.

    If the network is open, password is not needed.
    If protected, provide the password.
    """
    ssid_clean = ssid.strip()
    if not ssid_clean:
        return "No SSID provided for WiFi connection."

    if password:
        ok, _, stderr = _run_nmcli(
            ["device", "wifi", "connect", ssid_clean, "password", password],
        )
    else:
        ok, _, stderr = _run_nmcli(
            ["device", "wifi", "connect", ssid_clean],
        )

    if ok:
        return f"Connected to WiFi: {ssid_clean}"
    err_msg = stderr or "unknown error"
    return f"Failed to connect to '{ssid_clean}': {err_msg}"


def disconnect_wifi() -> str:
    """Disconnect from the current WiFi network."""
    # First find the wifi interface
    ok, stdout, stderr = _run_nmcli(
        ["-t", "-f", "TYPE,DEVICE", "device", "status"],
    )
    if not ok:
        return f"Failed to get device list: {stderr}"

    wifi_iface = None
    for line in stdout.splitlines():
        if line.startswith("wifi:"):
            wifi_iface = line.split(":")[-1].strip()
            break

    if not wifi_iface:
        # Try common names
        for iface in ("wlan0", "wlp2s0", "wlp3s0", "wlp1s0"):
            if_ok, _, _ = _run_nmcli(["device", "show", iface])
            if if_ok:
                wifi_iface = iface
                break

    if not wifi_iface:
        return "No WiFi interface found to disconnect."

    ok, _, stderr = _run_nmcli(["device", "disconnect", wifi_iface])
    if ok:
        return f"Disconnected from WiFi ({wifi_iface})."
    return f"Failed to disconnect: {stderr}"


def wifi_status() -> str:
    """Return WiFi status — enabled/disabled, connected SSID, signal strength."""
    # Radio status
    radio_ok, radio_out, _ = _run_nmcli(["radio", "wifi"])
    if not radio_ok:
        return "Could not check WiFi radio status."

    radio_enabled = "enabled" in radio_out.lower()

    # Connection status
    conn_ok, conn_out, _ = _run_nmcli(
        ["-t", "-f", "TYPE,NAME,DEVICE", "connection", "show", "--active"],
    )
    wifi_conn = None
    for line in conn_out.splitlines():
        if line.startswith("wifi:"):
            parts = line.split(":")
            if len(parts) >= 2:
                wifi_conn = parts[1]

    # Signal strength
    signal = None
    if wifi_conn:
        sig_ok, sig_out, _ = _run_nmcli(
            ["-t", "-f", "SSID,SIGNAL", "device", "wifi"],
        )
        if sig_ok:
            for line in sig_out.splitlines():
                if ":" in line:
                    ssid_part, sig_part = line.split(":", 1)
                    if ssid_part == wifi_conn and sig_part.strip().isdigit():
                        signal = int(sig_part.strip())
                        break

    lines = [
        f"WiFi radio: {'enabled' if radio_enabled else 'disabled'}",
    ]
    if wifi_conn:
        lines.append(f"Connected to: {wifi_conn}")
        if signal is not None:
            bars = "█" * (signal // 20) + "░" * (5 - signal // 20)
            lines.append(f"Signal: {signal}% {bars}")
    else:
        lines.append("Not connected to any WiFi network.")

    return "\n".join(lines)


def wifi_on() -> str:
    """Enable WiFi radio."""
    ok, _, stderr = _run_nmcli(["radio", "wifi", "on"])
    if ok:
        return "WiFi enabled."
    return f"Failed to enable WiFi: {stderr}"


def wifi_off() -> str:
    """Disable WiFi radio."""
    ok, _, stderr = _run_nmcli(["radio", "wifi", "off"])
    if ok:
        return "WiFi disabled."
    return f"Failed to disable WiFi: {stderr}"


def list_connections() -> str:
    """List all saved NetworkManager connections."""
    ok, stdout, stderr = _run_nmcli(
        ["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"],
    )
    if not ok:
        return f"Failed to list connections: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No saved connections found."

    result = ["Saved NetworkManager connections:"]
    for line in lines:
        parts = line.split(":")
        if len(parts) >= 2:
            name = parts[0]
            conn_type = parts[1]
            device = parts[2] if len(parts) > 2 else ""
            if conn_type == "wifi":
                dev_info = f" ({device})" if device else ""
                result.append(f"  WiFi: {name}{dev_info}")
            elif conn_type == "vpn":
                result.append(f"  VPN: {name}")
            elif conn_type == "ethernet":
                result.append(f"  Ethernet: {name}")
            else:
                result.append(f"  {conn_type}: {name}")

    if len(result) == 1:
        return "No saved connections found."

    return "\n".join(result)


def vpn_status() -> str:
    """Check if any VPN connection is active."""
    ok, stdout, stderr = _run_nmcli(
        ["-t", "-f", "TYPE,NAME", "connection", "show", "--active"],
    )
    if not ok:
        return f"Failed to check VPN status: {stderr or stdout}"

    vpns = []
    for line in stdout.splitlines():
        if line.startswith("vpn:"):
            parts = line.split(":")
            if len(parts) >= 2:
                vpns.append(parts[1])

    if vpns:
        return f"VPN active: {', '.join(vpns)}"
    return "No VPN connection active."
