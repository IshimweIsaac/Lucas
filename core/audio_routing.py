"""PipeWire audio routing for Lucas — list nodes, connections, and route audio between applications and outputs."""

from __future__ import annotations

import shutil

from core.logger import get_logger
from core.pc_control import _run

logger = get_logger(__name__)


def _check_pw_link() -> bool:
    """Check if pw-link is available."""
    return shutil.which("pw-link") is not None


def _check_pactl() -> bool:
    """Check if pactl is available."""
    return shutil.which("pactl") is not None


def list_audio_nodes() -> str:
    """List all audio nodes (sinks, sources, and filter nodes)."""
    if not _check_pw_link():
        return _pactl_fallback_nodes()
    lines = ["Audio Nodes:", ""]
    # Output ports (sinks)
    ok, stdout = _run(["pw-link", "-o"])
    if ok and stdout:
        lines.append("Output ports (Sinks):")
        for port in sorted(stdout.strip().splitlines()):
            port = port.strip()
            if port:
                lines.append(f"  {port}")
        lines.append("")
    # Input ports (sources)
    ok, stdout = _run(["pw-link", "-i"])
    if ok and stdout:
        lines.append("Input ports (Sources):")
        for port in sorted(stdout.strip().splitlines()):
            port = port.strip()
            if port:
                lines.append(f"  {port}")
    return "\n".join(lines) if len(lines) > 2 else "No audio nodes found."


def _pactl_fallback_nodes() -> str:
    """Fallback to pactl when pw-link is unavailable."""
    if not _check_pactl():
        return "Neither pw-link nor pactl available. Install pipewire-pulse."
    lines = ["Audio Nodes (via pactl):", ""]
    ok, stdout = _run(["pactl", "list", "sinks", "short"])
    if ok and stdout:
        lines.append("Sinks:")
        for line in stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                lines.append(f"  {parts[0]}: {parts[1]}")
    ok, stdout = _run(["pactl", "list", "sources", "short"])
    if ok and stdout:
        lines.append("Sources:")
        for line in stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                lines.append(f"  {parts[0]}: {parts[1]}")
    return "\n".join(lines)


def list_connections() -> str:
    """List current PipeWire connections between nodes."""
    if not _check_pw_link():
        return _pactl_fallback_connections()
    ok, stdout = _run(["pw-link", "-l"])
    if not ok or not stdout:
        return "No PipeWire connections found or pw-link unavailable."
    lines = ["Audio Connections:", ""]
    for line in stdout.strip().splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(f"  {stripped}")
    return "\n".join(lines)


def _pactl_fallback_connections() -> str:
    """Fallback: list sink-inputs and source-outputs."""
    if not _check_pactl():
        return "pw-link not available. Install pipewire (sudo dnf install pipewire)."
    lines = ["Active Audio Streams (via pactl):", ""]
    ok, stdout = _run(["pactl", "list", "sink-inputs", "short"])
    if ok and stdout:
        lines.append("Sink Inputs (audio playing):")
        for line in stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                lines.append(f"  ID {parts[0]}")
    ok, stdout = _run(["pactl", "list", "source-outputs", "short"])
    if ok and stdout:
        lines.append("Source Outputs (audio recording):")
        for line in stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                lines.append(f"  ID {parts[0]}")
    return "\n".join(lines)


def list_applications_audio() -> str:
    """List applications currently playing or recording audio.

    Uses pactl to find sink-inputs and source-outputs with app names.
    """
    if not _check_pactl():
        return "pactl not available. Install pipewire-pulse."
    lines = ["Applications with Audio:", ""]
    # Sink inputs (playing audio)
    ok, stdout = _run(["pactl", "list", "sink-inputs"])
    if ok and stdout:
        lines.extend(_parse_sink_inputs(stdout))
    # Source outputs (recording audio)
    ok, stdout = _run(["pactl", "list", "source-outputs"])
    if ok and stdout:
        lines.extend(_parse_source_outputs(stdout))
    if len(lines) <= 2:
        return "No applications currently using audio."
    return "\n".join(lines)


def _parse_sink_inputs(output: str) -> list[str]:
    """Parse pactl sink-inputs output to extract app name and stream info."""
    lines: list[str] = []
    current_id = ""
    app_name = ""
    in_section = False
    for line in output.splitlines():
        if line.startswith("Sink Input #"):
            if in_section and app_name:
                lines.append(f"  Playing: {app_name} (ID {current_id})")
            current_id = line.split("#")[-1].strip()
            app_name = ""
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("application.name = "):
                app_name = stripped.split("=", 1)[-1].strip().strip('"')
            elif stripped.startswith("application.process.binary = "):
                if not app_name:
                    app_name = stripped.split("=", 1)[-1].strip().strip('"')
    if in_section and app_name:
        lines.append(f"  Playing: {app_name} (ID {current_id})")
    return lines


def _parse_source_outputs(output: str) -> list[str]:
    """Parse pactl source-outputs output to extract app name."""
    lines: list[str] = []
    current_id = ""
    app_name = ""
    in_section = False
    for line in output.splitlines():
        if line.startswith("Source Output #"):
            if in_section and app_name:
                lines.append(f"  Recording: {app_name} (ID {current_id})")
            current_id = line.split("#")[-1].strip()
            app_name = ""
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("application.name = "):
                app_name = stripped.split("=", 1)[-1].strip().strip('"')
            elif stripped.startswith("application.process.binary = "):
                if not app_name:
                    app_name = stripped.split("=", 1)[-1].strip().strip('"')
    if in_section and app_name:
        lines.append(f"  Recording: {app_name} (ID {current_id})")
    return lines


def connect_node(source_port: str, target_port: str) -> str:
    """Connect two PipeWire nodes."""
    if not _check_pw_link():
        return "pw-link not available. Install pipewire (sudo dnf install pipewire)."
    if not source_port or not target_port:
        return "Provide both source_port and target_port."
    r = _run(["pw-link", "connect", source_port, target_port])
    if r.ok:
        return f"Connected: {source_port} -> {target_port}"
    return f"Failed to connect: {r.stderr or 'unknown error'}"


def disconnect_node(source_port: str, target_port: str) -> str:
    """Disconnect two PipeWire nodes."""
    if not _check_pw_link():
        return "pw-link not available. Install pipewire (sudo dnf install pipewire)."
    if not source_port or not target_port:
        return "Provide both source_port and target_port."
    r = _run(["pw-link", "disconnect", source_port, target_port])
    if r.ok:
        return f"Disconnected: {source_port} -> {target_port}"
    return f"Failed to disconnect: {r.stderr or 'unknown error'}"


def _find_sink_input_by_app(app_name: str) -> list[int]:
    """Find sink-input IDs for a given application name.

    Returns list of matching IDs.
    """
    if not _check_pactl():
        return []
    ok, stdout = _run(["pactl", "list", "sink-inputs"])
    if not ok or not stdout:
        return []
    ids: list[int] = []
    current_id = 0
    app_lower = app_name.lower()
    in_section = False
    for line in stdout.splitlines():
        if line.startswith("Sink Input #"):
            current_id_str = line.split("#")[-1].strip()
            try:
                current_id = int(current_id_str)
            except ValueError:
                current_id = 0
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("application.name = ") or stripped.startswith(
                "application.process.binary = "
            ):
                val = stripped.split("=", 1)[-1].strip().strip('"').lower()
                if app_lower in val:
                    if current_id > 0:
                        ids.append(current_id)
            elif stripped.startswith("application.process.id = "):
                in_section = False
    return ids


def mute_application(app_name: str, mute: bool = True) -> str:
    """Mute or unmute a specific application's audio.

    Uses pactl to find sink-inputs by application name and toggle mute.
    """
    if not _check_pactl():
        return "pactl not available. Install pipewire-pulse."
    ids = _find_sink_input_by_app(app_name)
    if not ids:
        return f"No audio stream found for '{app_name}'."
    mute_val = "1" if mute else "0"
    action = "muted" if mute else "unmuted"
    results: list[str] = []
    for sid in ids:
        r = _run(["pactl", "set-sink-input-mute", str(sid), mute_val])
        if r.ok:
            results.append(f"Sink input {sid} {action}")
        else:
            results.append(f"Failed to {action} sink input {sid}")
    if not results:
        return f"No audio streams found for '{app_name}'."
    return "; ".join(results)


def route_application_to_output(app_name: str, sink_name: str) -> str:
    """Move an application's audio to a specific output.

    Uses pactl to find sink-inputs by app name and move them.
    """
    if not _check_pactl():
        return "pactl not available. Install pipewire-pulse."
    ids = _find_sink_input_by_app(app_name)
    if not ids:
        return f"No audio stream found for '{app_name}'."
    # Find the sink by name (partial match)
    target_sink = _resolve_sink_name(sink_name)
    if target_sink is None:
        return f"No sink found matching '{sink_name}'. Use list_audio_nodes to see available sinks."
    results: list[str] = []
    for sid in ids:
        r = _run(["pactl", "move-sink-input", str(sid), target_sink])
        if r.ok:
            results.append(f"Moved {sid} to {target_sink}")
        else:
            results.append(f"Failed to move {sid}")
    return "; ".join(results) if results else "No streams moved."


def _resolve_sink_name(partial: str) -> str | None:
    """Find the first sink whose name contains the given partial string."""
    ok, stdout = _run(["pactl", "list", "sinks", "short"])
    if not ok or not stdout:
        return None
    partial_lower = partial.lower()
    best_match = None
    for line in stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            sink_name = parts[1]
            if partial_lower in sink_name.lower():
                # Prefer exact match
                if sink_name.lower() == partial_lower:
                    return sink_name
                if best_match is None:
                    best_match = sink_name
    return best_match
