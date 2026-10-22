"""Tests for actions/screen_processor.py — screen/camera capture and vision analysis.

Strategy: mock all external dependencies (mss, cv2, PIL, sounddevice, google.genai)
and test pure functions, fallback paths, and the main dispatch logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from actions import screen_processor as sp_mod
from actions.screen_processor import (
    TOOL_SCHEMA,
    _capture_screen,
    _compress,
    _cv2_backend,
    _detect_camera_index,
    _get_api_key,
    _get_camera_index,
    _get_os,
    _load_config,
    _probe_camera,
    _save_config_key,
    screen_process,
    warmup_session,
)


# ---------------------------------------------------------------------------
# TOOL_SCHEMA
# ---------------------------------------------------------------------------


def test_tool_schema_name():
    assert TOOL_SCHEMA["name"] == "screen_process"


def test_tool_schema_description():
    desc = TOOL_SCHEMA["description"]
    assert "screen" in desc or "capture" in desc
    assert "analyze" in desc


def test_tool_schema_parameters():
    props = TOOL_SCHEMA["parameters"]["properties"]
    assert "angle" in props
    assert "text" in props
    assert props["angle"]["type"] == "STRING"
    assert props["text"]["type"] == "STRING"


def test_tool_schema_required_text():
    assert TOOL_SCHEMA["parameters"]["required"] == ["text"]


# ---------------------------------------------------------------------------
# _compress
# ---------------------------------------------------------------------------


def test_compress_without_pil(monkeypatch):
    """When _PIL is False, return raw bytes unchanged."""
    monkeypatch.setattr(sp_mod, "_PIL", False)
    raw = b"fake_image_bytes"
    data, mime = _compress(raw, "PNG")
    assert data == raw
    assert mime == "image/png"


def test_compress_with_pil(monkeypatch):
    """When _PIL is True, resize and convert to JPEG."""
    monkeypatch.setattr(sp_mod, "_PIL", True)

    # Create a tiny real PNG so PIL can open it
    import struct
    import zlib

    def _make_png(w: int, h: int) -> bytes:
        raw_data = b""
        for y in range(h):
            raw_data += b"\x00" + b"\xff\x00\x00" * w  # filter byte + red pixels
        compressed = zlib.compress(raw_data)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        chunk_ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr
        chunk_ihdr += struct.pack(">I", zlib.crc32(chunk_ihdr[4:]) & 0xFFFFFFFF)
        chunk_idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed
        chunk_idat += struct.pack(">I", zlib.crc32(chunk_idat[4:]) & 0xFFFFFFFF)
        iend = struct.pack(">I", 0) + b"IEND"
        iend += struct.pack(">I", zlib.crc32(iend[4:]) & 0xFFFFFFFF)
        return b"\x89PNG\r\n\x1a\n" + chunk_ihdr + chunk_idat + iend

    png_data = _make_png(100, 50)
    data, mime = _compress(png_data, "PNG")
    assert mime == "image/jpeg"
    # Should be smaller than original (or at least different)
    assert len(data) < len(png_data) or data != png_data


def test_compress_pil_fallback_on_error(monkeypatch):
    """If PIL processing fails, return original bytes."""
    monkeypatch.setattr(sp_mod, "_PIL", True)
    raw = b"not a real image"
    data, mime = _compress(raw, "PNG")
    assert data == raw
    assert mime == "image/png"


# ---------------------------------------------------------------------------
# _cv2_backend
# ---------------------------------------------------------------------------


def test_cv2_backend_without_cv2(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", False)
    assert _cv2_backend() == 0


def test_cv2_backend_windows(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    monkeypatch.setattr(sp_mod, "_get_os", lambda: "windows")
    import cv2
    assert _cv2_backend() == cv2.CAP_DSHOW


def test_cv2_backend_mac(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    monkeypatch.setattr(sp_mod, "_get_os", lambda: "mac")
    import cv2
    assert _cv2_backend() == cv2.CAP_AVFOUNDATION


def test_cv2_backend_linux(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    monkeypatch.setattr(sp_mod, "_get_os", lambda: "linux")
    import cv2
    assert _cv2_backend() == cv2.CAP_ANY


# ---------------------------------------------------------------------------
# _probe_camera
# ---------------------------------------------------------------------------


def test_probe_camera_without_cv2(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", False)
    assert _probe_camera(0, 0) is False


def test_probe_camera_no_opened(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    mock_cv2 = MagicMock()
    monkeypatch.setattr(sp_mod, "cv2", mock_cv2)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_cv2.VideoCapture.return_value = mock_cap
    assert _probe_camera(0, 0) is False
    mock_cap.release.assert_called_once()


def test_probe_camera_no_frame(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    mock_cv2 = MagicMock()
    monkeypatch.setattr(sp_mod, "cv2", mock_cv2)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    # warmup=5 reads, then one final read that returns (False, None)
    fake_frame = MagicMock()
    mock_cap.read.side_effect = [(True, fake_frame)] * 5 + [(False, None)]
    mock_cv2.VideoCapture.return_value = mock_cap
    assert _probe_camera(0, 0) is False


def test_probe_camera_success(monkeypatch):
    monkeypatch.setattr(sp_mod, "_CV2", True)
    mock_cv2 = MagicMock()
    monkeypatch.setattr(sp_mod, "cv2", mock_cv2)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    frame = MagicMock()
    # warmup=5 reads, then one final read that returns (True, frame)
    mock_cap.read.side_effect = [(True, frame)] * 5 + [(True, frame)]
    mock_cv2.VideoCapture.return_value = mock_cap
    monkeypatch.setattr(sp_mod, "np", MagicMock())
    sp_mod.np.mean.return_value = 100  # > 8 → success
    assert _probe_camera(0, 0) is True


# ---------------------------------------------------------------------------
# _detect_camera_index
# ---------------------------------------------------------------------------


def test_detect_camera_index_found(monkeypatch):
    monkeypatch.setattr(sp_mod, "_cv2_backend", lambda: 0)
    # Index 0 fails, index 2 succeeds
    call_count = [0]

    def fake_probe(idx, backend):
        call_count[0] += 1
        return idx == 2

    monkeypatch.setattr(sp_mod, "_probe_camera", fake_probe)
    saved = {}
    monkeypatch.setattr(sp_mod, "_save_config_key", lambda k, v: saved.update({k: v}))
    result = _detect_camera_index()
    assert result == 2
    assert saved.get("camera_index") == 2


def test_detect_camera_index_not_found(monkeypatch):
    monkeypatch.setattr(sp_mod, "_cv2_backend", lambda: 0)
    monkeypatch.setattr(sp_mod, "_probe_camera", lambda i, b: False)
    saved = {}
    monkeypatch.setattr(sp_mod, "_save_config_key", lambda k, v: saved.update({k: v}))
    result = _detect_camera_index()
    assert result == 0  # default fallback
    assert saved.get("camera_index") == 0


# ---------------------------------------------------------------------------
# _get_camera_index
# ---------------------------------------------------------------------------


def test_get_camera_index_from_config(monkeypatch):
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {"camera_index": 3})
    assert _get_camera_index() == 3


def test_get_camera_index_fallback_to_detect(monkeypatch):
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {})
    monkeypatch.setattr(sp_mod, "_detect_camera_index", lambda: 1)
    assert _get_camera_index() == 1


# ---------------------------------------------------------------------------
# _load_config / _save_config_key
# ---------------------------------------------------------------------------


def test_load_config(monkeypatch):
    monkeypatch.setattr(sp_mod, "load_api_keys", lambda: {"gemini_api_key": "test-key"})
    cfg = _load_config()
    assert cfg.get("gemini_api_key") == "test-key"


def test_save_config_key(tmp_path, monkeypatch):
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {"existing": "value"})
    config_file = tmp_path / "test_keys.json"
    monkeypatch.setattr(sp_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(sp_mod, "logger", MagicMock())
    _save_config_key("camera_index", 2)
    # Read the file directly to verify contents
    import json
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved.get("existing") == "value"
    assert saved.get("camera_index") == 2


def test_save_config_key_handles_error(monkeypatch):
    """_save_config_key logs warning on write failure."""
    mock_logger = MagicMock()
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {"k": "v"})

    def _bad_write(*args, **kwargs):
        raise PermissionError("no write access")

    bad_path = MagicMock()
    bad_path.write_text = _bad_write
    monkeypatch.setattr(sp_mod, "CONFIG_FILE", bad_path)
    monkeypatch.setattr(sp_mod, "logger", mock_logger)
    # Should not raise
    _save_config_key("test", 1)
    mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# _get_api_key
# ---------------------------------------------------------------------------


def test_get_api_key_success(monkeypatch):
    monkeypatch.setattr(sp_mod, "get_gemini_key", lambda: "valid-key-123")
    assert _get_api_key() == "valid-key-123"


def test_get_api_key_missing_raises(monkeypatch):
    monkeypatch.setattr(sp_mod, "get_gemini_key", lambda: None)
    with pytest.raises(RuntimeError, match="gemini_api_key not found"):
        _get_api_key()


# ---------------------------------------------------------------------------
# _get_os
# ---------------------------------------------------------------------------


def test_get_os_from_config(monkeypatch):
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {"os_system": "mac"})
    assert _get_os() == "mac"


def test_get_os_default_windows(monkeypatch):
    monkeypatch.setattr(sp_mod, "_load_config", lambda: {})
    assert _get_os() == "windows"


# ---------------------------------------------------------------------------
# _capture_screen
# ---------------------------------------------------------------------------


def test_capture_screen_without_mss_raises(monkeypatch):
    monkeypatch.setattr(sp_mod, "_MSS", False)
    # Prevent Wayland gnome-screenshot branch from executing
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(RuntimeError, match="mss is not installed"):
        _capture_screen()


def test_capture_screen_with_mss_calls_compress(monkeypatch):
    """With MSS enabled, capture should succeed."""
    monkeypatch.setattr(sp_mod, "_MSS", True)
    monkeypatch.setattr(sp_mod, "_PIL", False)  # skip PIL compression
    # Prevent Wayland branch from executing
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    # Mock mss module
    mock_mss = MagicMock()
    monkeypatch.setattr(sp_mod, "mss", mock_mss)
    # mss.tools is accessed as mss.tools, not a separate module attr
    mock_mss.tools.to_png.return_value = b"fake_png_bytes"

    mock_sct = MagicMock()
    mock_mss.mss.return_value.__enter__.return_value = mock_sct
    mock_sct.monitors = [MagicMock(), MagicMock()]
    mock_shot = MagicMock()
    mock_sct.grab.return_value = mock_shot
    mock_shot.rgb = b"fake_rgb"
    mock_shot.size = (100, 50)

    data, mime = _capture_screen()
    assert data == b"fake_png_bytes"
    assert mime == "image/png"


def test_capture_screen_mss_with_compress(monkeypatch):
    """With both MSS and PIL enabled, compress is called."""
    monkeypatch.setattr(sp_mod, "_MSS", True)
    monkeypatch.setattr(sp_mod, "_PIL", True)
    # Prevent Wayland branch from executing
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    mock_mss = MagicMock()
    monkeypatch.setattr(sp_mod, "mss", mock_mss)
    mock_mss.tools.to_png.return_value = b"not_a_real_png"

    mock_sct = MagicMock()
    mock_mss.mss.return_value.__enter__.return_value = mock_sct
    mock_sct.monitors = [MagicMock(), MagicMock()]
    mock_shot = MagicMock()
    mock_sct.grab.return_value = mock_shot
    mock_shot.rgb = b"rgb"
    mock_shot.size = (10, 10)

    # Since PIL cannot open "not_a_real_png", compress returns raw bytes
    data, mime = _capture_screen()
    assert data == b"not_a_real_png"


# ---------------------------------------------------------------------------
# screen_process() — main dispatcher
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_screen_process_deps(monkeypatch):
    """Mock _ensure_session, _capture_screen, _session.analyze for dispatch tests."""
    # Make _ensure_session a no-op
    monkeypatch.setattr(sp_mod, "_ensure_session", lambda player=None: None)
    # Mock _capture_screen to return known data
    monkeypatch.setattr(
        sp_mod, "_capture_screen", lambda: (b"screen_data", "image/png")
    )
    # Mock _session.analyze
    mock_session = MagicMock()
    monkeypatch.setattr(sp_mod, "_session", mock_session)
    return mock_session


def test_screen_process_no_text():
    """Empty or missing text returns an error."""
    result = screen_process(parameters={})
    assert "No question provided" in result

    result = screen_process(parameters={"text": ""})
    assert "No question provided" in result

    result = screen_process(parameters={"text": "   "})
    assert "No question provided" in result


def test_screen_process_capture_error(mock_screen_process_deps, monkeypatch):
    """When _capture_screen raises, return the error message."""
    import unittest.mock as um
    with um.patch.object(sp_mod, "_capture_screen", side_effect=RuntimeError("boom")):
        result = screen_process(parameters={"text": "what do you see?"})
    assert "Capture error" in result
    assert "boom" in result


def test_screen_process_session_start_failure(monkeypatch):
    """When _ensure_session raises, return error."""
    import unittest.mock as um
    with um.patch.object(sp_mod, "_ensure_session", side_effect=RuntimeError("connection failed")):
        result = screen_process(parameters={"text": "hello"})
    assert "Could not start session" in result
    assert "connection failed" in result


def test_screen_process_happy_path_screen(mock_screen_process_deps):
    """Happy path: angle='screen' captures screen and analyzes."""
    mock_session = mock_screen_process_deps
    result = screen_process(parameters={"text": "what do you see?", "angle": "screen"})
    assert result == "Done."
    mock_session.analyze.assert_called_once_with(
        b"screen_data", "image/png", "what do you see?"
    )


def test_screen_process_happy_path_camera(monkeypatch):
    """Happy path: angle='camera' captures camera and analyzes."""
    monkeypatch.setattr(sp_mod, "_ensure_session", lambda player=None: None)
    monkeypatch.setattr(
        sp_mod, "_capture_camera", lambda: (b"camera_data", "image/jpeg")
    )
    mock_session = MagicMock()
    monkeypatch.setattr(sp_mod, "_session", mock_session)
    result = screen_process(parameters={"text": "who am I?", "angle": "camera"})
    assert result == "Done."
    mock_session.analyze.assert_called_once_with(
        b"camera_data", "image/jpeg", "who am I?"
    )


def test_screen_process_default_angle(monkeypatch):
    """Default angle is 'screen' when not specified."""
    monkeypatch.setattr(sp_mod, "_ensure_session", lambda player=None: None)
    mock_capture = MagicMock(return_value=(b"data", "image/png"))
    monkeypatch.setattr(sp_mod, "_capture_screen", mock_capture)
    mock_session = MagicMock()
    monkeypatch.setattr(sp_mod, "_session", mock_session)
    screen_process(parameters={"text": "test"})
    mock_capture.assert_called_once()


def test_screen_process_with_player_logs(monkeypatch):
    """When player is provided, screen_process logs."""
    monkeypatch.setattr(sp_mod, "_ensure_session", lambda player=None: None)
    monkeypatch.setattr(
        sp_mod, "_capture_screen", lambda: (b"data", "image/png")
    )
    mock_session = MagicMock()
    monkeypatch.setattr(sp_mod, "_session", mock_session)
    mock_player = MagicMock()
    result = screen_process(parameters={"text": "test"}, player=mock_player)
    assert result == "Done."


# ---------------------------------------------------------------------------
# warmup_session
# ---------------------------------------------------------------------------


def test_warmup_session_calls_ensure_session(monkeypatch):
    called = False

    def fake_ensure(player=None):
        nonlocal called
        called = True
        assert player is None

    monkeypatch.setattr(sp_mod, "_ensure_session", fake_ensure)
    warmup_session()
    assert called


def test_warmup_session_handles_exception(monkeypatch):
    """warmup_session should not raise if _ensure_session fails."""
    import unittest.mock as um
    with um.patch.object(sp_mod, "_ensure_session", side_effect=RuntimeError("fail")):
        # Should not raise
        warmup_session()


# ---------------------------------------------------------------------------
# _VisionSession import / structure
# ---------------------------------------------------------------------------


def test_vision_session_class_exists():
    from actions.screen_processor import _VisionSession
    assert hasattr(_VisionSession, "start")
    assert hasattr(_VisionSession, "analyze")
    assert hasattr(_VisionSession, "is_ready")


def test_session_constants():
    assert sp_mod._IMG_MAX_W > 0
    assert sp_mod._IMG_MAX_H > 0
    assert 0 < sp_mod._JPEG_Q <= 100
    assert sp_mod._SYSTEM_PROMPT is not None
    assert "LUCAS" in sp_mod._SYSTEM_PROMPT
