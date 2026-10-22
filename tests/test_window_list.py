from __future__ import annotations

from core import window_list as wl


def test_parse_extension_list_output():
    raw = "[{'title': 'Firefox', 'id': 1, 'class': 'firefox'}]"
    wins = wl._parse_extension_list_output(raw)
    assert len(wins) == 1
    assert wins[0]["title"] == "Firefox"


def test_list_windows_process(monkeypatch):
    monkeypatch.setattr(wl, "gnome_shell", wl.gnome_shell)
    monkeypatch.setattr(
        wl.gnome_shell,
        "shell_available",
        lambda env=None: False,
    )
    monkeypatch.setattr(wl, "_gdbus_extension_list", lambda *a, **k: [])
    monkeypatch.setattr(wl, "_list_windows_wmctrl", lambda: [])
    monkeypatch.setattr(wl, "_is_wayland", lambda: True)
    monkeypatch.setattr(
        wl,
        "_run",
        lambda cmd, **kw: (
            True,
            "1234 firefox\n5678 cursor\n",
        )
        if "ps" in cmd[0]
        else (False, ""),
    )
    monkeypatch.setenv("USER", "testuser")
    wins = wl.list_windows()
    assert any("firefox" in w["title"].lower() for w in wins)
