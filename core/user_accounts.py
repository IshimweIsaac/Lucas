"""User account information (read-only).

Provides functions to list human user accounts on the system and
identify the current logged-in user.
"""

from __future__ import annotations

import os
import pwd
import subprocess

from core.logger import get_logger

logger = get_logger(__name__)


def list_users() -> str:
    """List human user accounts by reading /etc/passwd.

    Returns users with UID >= 1000 and UID != 65534 (nobody).
    """
    users: list[dict[str, str | int]] = []
    try:
        for entry in pwd.getpwall():
            if entry.pw_uid >= 1000 and entry.pw_uid != 65534:
                users.append(
                    {
                        "name": entry.pw_name,
                        "uid": entry.pw_uid,
                        "gid": entry.pw_gid,
                        "home": entry.pw_dir,
                        "shell": entry.pw_shell,
                    }
                )
    except Exception as e:
        logger.error("list_users error: %s", e)
        try:
            # Fallback to /etc/passwd parsing
            result = subprocess.run(
                ["awk", "-F:", "$3>=1000 && $3!=65534 {print $1}", "/etc/passwd"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
                if names:
                    return f"Users ({len(names)}):\n  " + "\n  ".join(names)
            return f"Failed to list users: {result.stderr.strip()}"
        except Exception as e2:
            return f"Failed to list users: {e2}"

    if not users:
        return "No human users found."

    lines: list[str] = [f"Users ({len(users)}):"]
    for u in users:
        lines.append(
            f"  {u['name']} (uid={u['uid']}, home={u['home']}, shell={u['shell']})"
        )
    return "\n".join(lines)


def current_user() -> str:
    """Return the current username."""
    try:
        name = os.getlogin()
    except OSError:
        name = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    return f"Current user: {name}"
