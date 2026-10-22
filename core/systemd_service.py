"""Install Lucas as a systemd user service (Linux)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from memory.config_manager import get_base_dir

SERVICE_NAME = "lucas.service"
UNIT_PATH = Path.home() / ".config/systemd/user" / SERVICE_NAME


def _unit_content(repo: Path, python: str) -> str:
    return f"""[Unit]
Description=LUCAS Voice Assistant
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory={repo}
ExecStart={python} {repo / "main.py"}
Restart=on-failure
RestartSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
"""


def install() -> str:
    if sys.platform.startswith("linux") is False:
        return "systemd user service is only supported on Linux."
    repo = get_base_dir()
    main_py = repo / "main.py"
    if not main_py.is_file():
        return f"Cannot find {main_py}"

    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(_unit_content(repo, sys.executable), encoding="utf-8")

    wake_flag = Path.home() / ".lucas" / "wake_on_alert"
    wake_flag.parent.mkdir(parents=True, exist_ok=True)
    wake_flag.touch()

    steps = [
        (["systemctl", "--user", "daemon-reload"], "daemon-reload"),
        (["systemctl", "--user", "enable", SERVICE_NAME], "enable"),
        (["systemctl", "--user", "start", SERVICE_NAME], "start"),
    ]
    for cmd, label in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout).strip()
            return f"Failed at {label}: {err}"

    return (
        f"Installed {UNIT_PATH}. Lucas should start at login and on wake alerts. "
        "Check: systemctl --user status lucas"
    )


def uninstall() -> str:
    if not UNIT_PATH.exists():
        return "Lucas systemd service is not installed."
    for cmd in (
        ["systemctl", "--user", "stop", SERVICE_NAME],
        ["systemctl", "--user", "disable", SERVICE_NAME],
    ):
        subprocess.run(cmd, capture_output=True)
    UNIT_PATH.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return "Lucas user service removed."


def status() -> str:
    if not UNIT_PATH.exists():
        return "Not installed. Use action install on Linux."
    r = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    active = (r.stdout or "").strip()
    r2 = subprocess.run(
        ["systemctl", "--user", "status", SERVICE_NAME, "--no-pager", "-n", "8"],
        capture_output=True,
        text=True,
    )
    body = (r2.stdout or r2.stderr or "").strip()[:1200]
    return f"Service state: {active}\n{body}"
