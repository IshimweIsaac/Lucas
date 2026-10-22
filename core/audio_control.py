"""Audio device management via PipeWire/PulseAudio (pactl)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)


def _run_pactl(args: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a pactl command and return (ok, stdout, stderr)."""
    cmd = ["pactl", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "pactl not found — is PipeWire/PulseAudio installed?"
    except subprocess.TimeoutExpired:
        return False, "", f"pactl timed out: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"pactl error: {e}"


def _parse_pactl_list_sinks(output: str) -> list[dict]:
    """Parse 'pactl list short sinks' output into structured dicts."""
    sinks: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "id	name	driver	s	state	volume	..."
        parts = line.split("\t")
        if len(parts) >= 2:
            sink = {
                "id": parts[0],
                "name": parts[1],
                "state": parts[4] if len(parts) > 4 else "?",
            }
            sinks.append(sink)
    return sinks


def _parse_pactl_list_sources(output: str) -> list[dict]:
    """Parse 'pactl list short sources' output into structured dicts."""
    sources: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            source = {
                "id": parts[0],
                "name": parts[1],
                "state": parts[4] if len(parts) > 4 else "?",
            }
            sources.append(source)
    return sources


def list_sinks() -> str:
    """List available audio output sinks (speakers, headphones, etc.)."""
    ok, stdout, stderr = _run_pactl(["list", "short", "sinks"])
    if not ok:
        return f"Failed to list sinks: {stderr or stdout}"

    sinks = _parse_pactl_list_sinks(stdout)
    if not sinks:
        return "No audio sinks found."

    # Get default sink
    default_ok, default_out, _ = _run_pactl(["get-default-sink"])
    default_sink = default_out.strip() if default_ok else ""

    lines = [f"Audio sinks ({len(sinks)} found):"]
    for s in sinks:
        is_default = " [default]" if s["name"] == default_sink else ""
        lines.append(f"  #{s['id']}: {s['name']}{is_default}")
    return "\n".join(lines)


def list_sources() -> str:
    """List available audio input sources (microphones, line-in, etc.)."""
    ok, stdout, stderr = _run_pactl(["list", "short", "sources"])
    if not ok:
        return f"Failed to list sources: {stderr or stdout}"

    sources = _parse_pactl_list_sources(stdout)
    if not sources:
        return "No audio sources found."

    # Get default source
    default_ok, default_out, _ = _run_pactl(["get-default-source"])
    default_source = default_out.strip() if default_ok else ""

    lines = [f"Audio sources ({len(sources)} found):"]
    for s in sources:
        is_default = " [default]" if s["name"] == default_source else ""
        lines.append(f"  #{s['id']}: {s['name']}{is_default}")
    return "\n".join(lines)


def set_default_sink(name: str) -> str:
    """Set the default audio output sink by name."""
    if not name.strip():
        return "No sink name provided."

    ok, _, stderr = _run_pactl(["set-default-sink", name.strip()])
    if ok:
        return f"Default audio output set to: {name.strip()}"
    return f"Failed to set default sink: {stderr}"


def set_default_source(name: str) -> str:
    """Set the default audio input source by name."""
    if not name.strip():
        return "No source name provided."

    ok, _, stderr = _run_pactl(["set-default-source", name.strip()])
    if ok:
        return f"Default audio input set to: {name.strip()}"
    return f"Failed to set default source: {stderr}"


def list_applications() -> str:
    """List running applications with audio sink inputs."""
    ok, stdout, stderr = _run_pactl(["list", "short", "sink-inputs"])
    if not ok:
        return f"Failed to list audio applications: {stderr or stdout}"

    lines = stdout.splitlines()
    if not lines:
        return "No applications currently playing audio."

    # Get detailed info for each
    result = ["Applications with audio output:"]
    for line in lines:
        parts = line.strip().split("\t")
        if parts:
            input_id = parts[0]
            # Get application name from pactl list sink-inputs
            detail_ok, detail_out, _ = _run_pactl(
                ["list", "sink-inputs"],
            )
            app_name = None
            sink_name = None
            if detail_ok:
                current_id = None
                for dline in detail_out.splitlines():
                    dl = dline.strip()
                    if dl.startswith("Sink Input #") and f"#{input_id}" in dl:
                        current_id = input_id
                    elif current_id and "application.name" in dl:
                        app_name = dl.split("=", 1)[-1].strip().strip('"')
                    elif current_id and "Sink:" in dl:
                        sink_name = dl.split(":", 1)[-1].strip()
                        break

            parts_line = [f"  #{input_id}"]
            if app_name:
                parts_line.append(f"{app_name}")
            if sink_name:
                parts_line.append(f"(sink: {sink_name})")
            result.append(" ".join(parts_line))

    return "\n".join(result)


def move_application(sink_input_id: str, sink_name: str) -> str:
    """Move an application's audio to a different sink."""
    if not sink_input_id.strip():
        return "No sink-input ID provided."
    if not sink_name.strip():
        return "No sink name provided."

    ok, _, stderr = _run_pactl(
        ["move-sink-input", sink_input_id.strip(), sink_name.strip()],
    )
    if ok:
        return (
            f"Moved application #{sink_input_id} to sink: {sink_name.strip()}"
        )
    return f"Failed to move application: {stderr}"


def test_microphone(duration_sec: int = 3) -> str:
    """Record a short audio clip and play it back to test the microphone.

    Uses parec (PipeWire/PulseAudio record) and paplay (playback).
    """
    duration = max(1, min(10, int(duration_sec)))

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name).resolve()
    tmp.close()

    try:
        # Record
        logger.info("Testing microphone: recording %d seconds...", duration)
        record_result = subprocess.run(
            ["parec", "--channels=1", "--rate=44100",
             "--format=s16le", "--record",
             "--raw"],
            capture_output=True, timeout=duration + 2,
        )
        if record_result.returncode != 0:
            return (
                f"Microphone test failed (record): "
                f"{record_result.stderr.strip() or record_result.stdout.strip()}"
            )

        raw_data = record_result.stdout

        if not raw_data or len(raw_data) < 1000:
            return (
                "Microphone test: recorded very little or no audio. "
                "Check if microphone is connected and not muted."
            )

        # Convert raw s16le to a WAV-like playable format
        try:
            import wave
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(44100)
                wf.writeframes(raw_data)
        except Exception as wav_err:
            logger.warning("Could not write WAV for playback test: %s", wav_err)

        # Playback
        logger.info("Microphone test: playing back...")
        playback_result = subprocess.run(
            ["paplay", str(tmp_path)],
            capture_output=True, text=True, timeout=duration + 2,
        )
        if playback_result.returncode != 0:
            return (
                f"Recorded {len(raw_data) // 88200:.1f}s of audio but playback "
                f"failed: {playback_result.stderr.strip() or playback_result.stdout.strip()}"
            )

        recorded_secs = len(raw_data) / 88200  # 44100 * 2 bytes
        return (
            f"Microphone test passed. Recorded {recorded_secs:.1f}s and played it back. "
            f"File saved temporarily to {tmp_path}."
        )

    except subprocess.TimeoutExpired:
        return "Microphone test timed out."
    except FileNotFoundError as e:
        return (
            f"Required audio tool not found: {e.name}. "
            f"Install pulseaudio-utils (parec, paplay)."
        )
    except Exception as e:
        return f"Microphone test failed: {e}"
    finally:
        # Clean up temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
