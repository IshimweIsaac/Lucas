from __future__ import annotations

from unittest.mock import MagicMock

from core import alert_delivery as ad


def test_restart_lucas_systemd(monkeypatch):
    monkeypatch.setattr(ad, "_systemd_lucas_active", lambda: True)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout="active", stderr="")

    monkeypatch.setattr(ad.subprocess, "run", fake_run)
    assert ad.restart_lucas() == "systemd-restart"
    assert calls[0][:3] == ["systemctl", "--user", "restart"]


def test_restart_lucas_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr(ad, "_systemd_lucas_active", lambda: False)
    monkeypatch.setattr(ad, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ad.Path, "home", lambda: tmp_path)
    main_py = tmp_path / "main.py"
    main_py.write_text("# test\n", encoding="utf-8")
    popens = []
    monkeypatch.setattr(
        ad.subprocess,
        "Popen",
        lambda *a, **k: popens.append((a, k)) or MagicMock(),
    )
    assert ad.restart_lucas() == "spawn-restart"
    assert popens
    assert "LUCAS_RESTART" in popens[0][1]["env"]
