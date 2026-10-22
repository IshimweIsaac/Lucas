"""Load script-based tools from memory/custom_tools/manifest.json."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from memory.config_manager import get_base_dir

BASE_DIR = get_base_dir()
CUSTOM_DIR = BASE_DIR / "memory" / "custom_tools"
MANIFEST_PATH = CUSTOM_DIR / "manifest.json"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"tools": []}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"tools": []}
    except Exception:
        return {"tools": []}


def _save_manifest(data: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_script(script_path: Path, parameters: dict) -> str:
    if not script_path.is_file():
        return f"Custom tool script not found: {script_path.name}"
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(parameters or {}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(CUSTOM_DIR),
        )
    except subprocess.TimeoutExpired:
        return "Custom tool timed out after 60s."
    except Exception as e:
        return f"Custom tool failed: {e}"

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        return f"Custom tool error (exit {result.returncode}): {err or out or 'unknown'}"
    return out or "Done."


def _make_handler(script_name: str):
    script_path = CUSTOM_DIR / script_name

    def handler(parameters: dict, response=None, player=None, session_memory=None, speak=None) -> str:
        return _run_script(script_path, parameters)

    return handler


def register_custom_tools(register_fn) -> list[str]:
    """Register each manifest tool via tool_registry.register."""
    names: list[str] = []
    for entry in _load_manifest().get("tools", []):
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name or not _NAME_RE.match(name):
            continue
        schema = {
            "name": name,
            "description": entry.get("description", f"Custom tool {name}"),
            "parameters": entry.get("parameters")
            or {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "Input for the tool"},
                },
                "required": [],
            },
        }
        script = entry.get("script") or f"{name}.py"
        register_fn(
            name=name,
            schema=schema,
            handler=_make_handler(script),
            accepts_speak=False,
        )
        names.append(name)
    return names


def add_custom_tool(
    name: str,
    description: str,
    script_body: str,
    *,
    parameters: dict | None = None,
) -> str:
    if not _NAME_RE.match(name):
        return "Invalid name — use snake_case letters/numbers (e.g. my_tool)."

    script_path = CUSTOM_DIR / f"{name}.py"
    if script_path.exists():
        return f"Script already exists: {script_path}"

    header = '''"""Custom Lucas tool — JSON parameters on stdin, result on stdout."""
import json
import sys


def main() -> str:
    params = json.loads(sys.stdin.read() or "{}")
'''
    footer = "\n\nif __name__ == '__main__':\n    print(main())\n"
    script_path.write_text(header + script_body + footer, encoding="utf-8")

    data = _load_manifest()
    tools = [t for t in data.get("tools", []) if t.get("name") != name]
    tools.append(
        {
            "name": name,
            "description": description,
            "script": f"{name}.py",
            "parameters": parameters
            or {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "Input"},
                },
                "required": [],
            },
        }
    )
    data["tools"] = tools
    _save_manifest(data)
    return f"Created custom tool {name}. Reconnect voice session to use it in Live API."
