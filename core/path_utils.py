"""Canonical path resolution — fixes case, shortcuts, and hallucinated paths on Linux."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from memory.config_manager import get_base_dir

_HOME = Path.home()


@dataclass
class PathResult:
    ok: bool
    path: str = ""
    requested: str = ""
    message: str = ""
    suggestions: list[str] = field(default_factory=list)
    corrected: bool = False


def _xdg_or_default(env_key: str, default: Path) -> Path:
    val = os.environ.get(env_key, "").strip()
    if val and Path(val).exists():
        return Path(val)
    return default


def _home_subdir(env_key: str, *dir_names: str) -> Path:
    """Pick the first existing ~/DirName variant (Documents vs documents)."""
    xdg = _xdg_or_default(env_key, Path(""))
    if str(xdg) not in ("", "."):
        return xdg
    for name in dir_names:
        candidate = _HOME / name
        if candidate.exists():
            return candidate
    return _HOME / dir_names[0]


def shortcut_map() -> dict[str, Path]:
    return {
        "root": Path(__file__).resolve().parent.parent,
        "lucas": Path(__file__).resolve().parent.parent,
        "lumina": _HOME / "Documents" / "Lumina",
        "desktop": _home_subdir("XDG_DESKTOP_DIR", "Desktop", "desktop"),
        "downloads": _home_subdir("XDG_DOWNLOAD_DIR", "Downloads", "downloads"),
        "documents": _home_subdir("XDG_DOCUMENTS_DIR", "Documents", "documents"),
        "pictures": _home_subdir("XDG_PICTURES_DIR", "Pictures", "pictures"),
        "music": _home_subdir("XDG_MUSIC_DIR", "Music", "music"),
        "videos": _home_subdir("XDG_VIDEOS_DIR", "Videos", "videos"),
        "home": _HOME,
    }


def known_paths() -> list[str]:
    """Real paths Lucas may cite — injected into session brief."""
    paths: list[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        try:
            resolved = str(Path(p).expanduser().resolve())
        except Exception:
            return
        if resolved not in seen and Path(resolved).exists():
            seen.add(resolved)
            paths.append(resolved)

    for p in shortcut_map().values():
        add(str(p))

    try:
        from memory.session_brief import load_brief

        ws = (load_brief().get("coding_workspace") or "").strip()
        if ws:
            add(ws)
    except Exception:
        pass

    profile = get_base_dir() / "memory" / "coding_profile.json"
    if profile.exists():
        try:
            import json

            data = json.loads(profile.read_text(encoding="utf-8"))
            root = (data.get("workspace_root") or "").strip()
            if root:
                add(root)
        except Exception:
            pass

    return sorted(paths)


def _canonicalize_case(path: Path) -> Path | None:
    """
    Fix wrong case only when the path does not exist yet.

    If ~/documents exists (lowercase) and is spelled correctly, it is kept as-is.
    Case changes only when the typed path is missing and exactly one sibling
    matches case-insensitively (e.g. user typed MyApp but disk has myapp).
    """
    if path.exists():
        return path.resolve()

    parts = path.parts
    if not parts:
        return None

    if path.is_absolute():
        current = Path(parts[0])
        start = 1
    else:
        current = Path.cwd()
        start = 0

    for part in parts[start:]:
        if not current.is_dir():
            return None
        exact = current / part
        if exact.exists():
            current = exact
            continue
        matches = [
            child
            for child in current.iterdir()
            if child.name.lower() == part.lower()
        ]
        if len(matches) == 1:
            current = matches[0]
        else:
            return None

    return current.resolve() if current.exists() else None


def _suggest_similar(path: Path, *, limit: int = 5) -> list[str]:
    out: list[str] = []
    name = path.name.lower()
    parent = path.parent

    if parent.exists() and parent.is_dir() and name:
        for child in sorted(parent.iterdir()):
            if name in child.name.lower() or child.name.lower() in name:
                out.append(str(child.resolve()))
            if len(out) >= limit:
                return out

    if "documents" in str(path).lower():
        docs = shortcut_map().get("documents", _HOME / "Documents")
        if docs.is_dir():
            for child in sorted(docs.iterdir())[:20]:
                if name and name in child.name.lower():
                    out.append(str(child.resolve()))
                if len(out) >= limit:
                    break

    for known in known_paths():
        if name and name in Path(known).name.lower():
            out.append(known)
        if len(out) >= limit:
            break

    return list(dict.fromkeys(out))[:limit]


def resolve_user_path(
    raw: str,
    *,
    must_exist: bool = True,
    must_be_dir: bool = False,
) -> PathResult:
    """
    Resolve shortcuts, ~, registry names, and fix filesystem case.

    Returns canonical absolute path when found.
    """
    text = (raw or "").strip()
    if not text:
        return PathResult(ok=False, requested=raw or "", message="Empty path.")

    low = text.lower().replace("\\", "/")
    shortcuts = shortcut_map()

    if low in shortcuts:
        target = shortcuts[low]
        return PathResult(
            ok=True,
            path=str(target.resolve()),
            requested=text,
            corrected=text != str(target),
            message="OK",
        )

    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (_HOME / candidate).resolve()

    fixed = _canonicalize_case(candidate)
    if fixed is not None:
        target = fixed
    else:
        target = candidate

    if must_exist and not target.exists():
        suggestions = _suggest_similar(candidate)
        msg = f"Path does not exist: {candidate}"
        if suggestions:
            msg += "\nDid you mean:\n" + "\n".join(f"  • {s}" for s in suggestions)
        msg += "\nUse path_helper action=resolve or file_controller action=list first."
        return PathResult(
            ok=False,
            requested=raw,
            message=msg,
            suggestions=suggestions,
        )

    if must_be_dir and target.exists() and not target.is_dir():
        return PathResult(
            ok=False,
            requested=raw,
            message=f"Not a directory: {target}",
        )

    canonical = str(target.resolve())
    return PathResult(
        ok=True,
        path=canonical,
        requested=raw,
        corrected=canonical != str(candidate),
        message="OK",
    )


def normalize_tool_paths(tool_name: str, args: dict) -> tuple[dict, str | None]:
    """
    Auto-fix path parameters when there is a unique match.

    Returns (updated_args, block_message). block_message stops the tool call.
    """
    path_keys = _PATH_KEYS.get(tool_name, ())
    if not path_keys:
        return args, None

    updated = dict(args)
    for key in path_keys:
        raw = (updated.get(key) or "").strip()
        if not raw:
            continue

        action = (updated.get("action") or "").lower()
        is_ws_key = key in ("workspace", "workspace_path")
        strict = tool_name in _STRICT_EXIST and key in (
            "path",
            "destination",
            "file_path",
        )
        must_exist = strict or is_ws_key
        if tool_name == "file_controller":
            must_exist = must_exist and _file_controller_must_exist(action, key)
        res = resolve_user_path(
            raw,
            must_exist=must_exist,
            must_be_dir=is_ws_key,
        )

        if res.ok:
            if res.path != raw:
                updated[key] = res.path
            continue

        if not strict and updated.get("action") in ("list", "find", "disk_usage", "info"):
            continue

        return updated, f"❌ {res.message}"

    return updated, None


_PATH_KEYS: dict[str, tuple[str, ...]] = {
    "file_controller": ("path", "destination"),
    "coding_workspace": ("workspace_path", "file_path", "path"),
    "open_app": ("path",),
}

_STRICT_EXIST = frozenset({"file_controller", "coding_workspace"})

# file_controller: targets that may not exist yet
_FILE_MAY_CREATE = frozenset({"create_folder", "create_file", "write"})
_FILE_DEST_NEW = frozenset({"copy", "move"})


def _file_controller_must_exist(action: str, key: str) -> bool:
    action = (action or "").lower()
    if action in _FILE_MAY_CREATE and key == "path":
        return False
    if action in _FILE_DEST_NEW and key == "destination":
        return False
    return True
