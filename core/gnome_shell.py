"""GNOME Shell window control on Wayland via org.gnome.Shell.Eval."""

from __future__ import annotations

import re
import subprocess

from core.logger import get_logger

log = get_logger(__name__)


def parse_eval_response(stdout: str) -> tuple[bool, str]:
    """Parse gdbus Eval output: ``(true, 'result')`` or ``(false, '')``."""
    s = (stdout or "").strip()
    if not s.startswith("("):
        return False, s
    if s.lower().startswith("(false"):
        return False, ""
    m = re.match(r"\(true,\s*'(.*)'\s*\)\s*$", s, re.DOTALL)
    if not m:
        m = re.match(r'\(true,\s*"(.*)"\s*\)\s*$', s, re.DOTALL)
    if not m:
        return False, s
    text = m.group(1)
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    text = text.replace("\\\\", "\x00").replace("\\'", "'").replace("\x00", "\\")
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    return True, text


def eval_js(js: str, *, env: dict[str, str] | None = None, timeout: int = 8) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Shell",
                "--object-path",
                "/org/gnome/Shell",
                "--method",
                "org.gnome.Shell.Eval",
                js,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            env=env,
        )
        if p.returncode != 0:
            log.debug("GNOME Shell Eval failed: %s", p.stderr)
            return False, (p.stderr or "").strip()
        return parse_eval_response((p.stdout or "").strip())
    except FileNotFoundError:
        return False, "gdbus not found"
    except subprocess.TimeoutExpired:
        return False, "GNOME Shell Eval timed out"
    except Exception as e:
        return False, str(e)


def shell_available(env: dict[str, str] | None = None) -> bool:
    ok, out = eval_js("String(1)", env=env)
    return ok and out == "1"


def _js_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def list_window_titles(env: dict[str, str] | None = None) -> list[str]:
    js = (
        "global.get_window_actors().map(a => a.meta_window.get_title())"
        ".filter(t => t).join('\\n')"
    )
    ok, out = eval_js(js, env=env)
    if not ok or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def focus_title_substring(match: str, env: dict[str, str] | None = None) -> str:
    m = _js_quote(match.strip().lower())
    if not m:
        return ""
    js = (
        "(() => {"
        f" let needle = '{m}';"
        " for (let a of global.get_window_actors()) {"
        "   let w = a.meta_window;"
        "   let t = (w.get_title() || '').toLowerCase();"
        "   if (t.includes(needle)) {"
        "     w.unminimize();"
        "     w.activate(global.get_current_time());"
        "     return w.get_title();"
        "   }"
        " }"
        " return '';"
        "})()"
    )
    ok, title = eval_js(js, env=env)
    return title if ok and title else ""


def close_title_substring(match: str, env: dict[str, str] | None = None) -> str:
    m = _js_quote(match.strip().lower())
    if not m:
        return ""
    js = (
        "(() => {"
        f" let needle = '{m}';"
        " for (let a of global.get_window_actors()) {"
        "   let w = a.meta_window;"
        "   let t = (w.get_title() || '').toLowerCase();"
        "   if (t.includes(needle)) {"
        "     let title = w.get_title();"
        "     w.delete(global.get_current_time());"
        "     return title;"
        "   }"
        " }"
        " return '';"
        "})()"
    )
    ok, title = eval_js(js, env=env)
    return title if ok and title else ""
