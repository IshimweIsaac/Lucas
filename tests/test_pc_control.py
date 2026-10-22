from __future__ import annotations

from unittest.mock import patch

from actions.pc_controller import pc_controller
from core import gnome_shell
from core import pc_control as pc


def test_gnome_parse_eval():
    ok, text = gnome_shell.parse_eval_response("(true, 'Chrome\\nFirefox')")
    assert ok is True
    assert "Chrome" in text and "Firefox" in text
    ok2, _ = gnome_shell.parse_eval_response("(false, '')")
    assert ok2 is False


def test_list_windows_delegates_to_window_list():
    from core import window_list

    with patch.object(
        window_list,
        "list_windows",
        return_value=[{"id": "0", "pid": "", "title": "YouTube", "source": "extension"}],
    ):
        wins = pc.list_windows()
    assert wins[0]["title"] == "YouTube"


def test_media_command_playerctl_all():
    with patch.object(pc, "_which", side_effect=lambda n: n == "playerctl"):
        with patch.object(pc, "_run", return_value=pc.CmdResult(True, "", "", 0)):
            assert "Media" in pc.media_command("pause")


def test_battery_low_when_discharging():
    with patch.object(
        pc,
        "battery_status",
        return_value={"percent": 15, "charging": False, "status": "discharging"},
    ):
        assert pc.battery_low(20) is True


def test_pc_controller_status():
    with patch.object(pc, "system_status_report", return_value="=== PC status ==="):
        out = pc_controller({"action": "status"})
        assert "PC status" in out


def test_volume_set():
    with patch.object(pc, "volume_set", return_value="Volume set to 40%."):
        assert "40" in pc_controller({"action": "volume_set", "value": 40})
