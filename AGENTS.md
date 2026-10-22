# Lucas — coding agent instructions

Read this before editing anything in this repository.

**Self-improvement backlog:** `memory/self_improvements.md` (ratings, challenge results, next fixes).

## Project layout

- `main.py` — voice/live entry; registers tools via `agent/tool_registry.py`
- `actions/` — one module per tool (`TOOL_SCHEMA` + handler function)
- `agent/` — planner, executor, orchestrator, error handler
- `agent/agents/` — small Aider-based agents (scout, coder, reviewer, fixer, builder)
- `agent/aider_runner.py` — single Aider subprocess wrapper (all agents use this)
- `agent/key_manager.py` — unified API key rotation for parallel agents
- `agent/search_agent.py` — Gemini research agent (uses `agent_keys.json`, not voice key)
- `tests/` — pytest suite; run before considering work done
- `memory/` — config and long-term memory (never commit API keys)
- `config/api_keys.json` — Gemini key (gitignored; do not read or modify in agent tasks)
- `config/agent_keys.json` — agent API keys for Gemini/Groq (gitignored; round-robin rotation)

## Coding LLM

- Repo coding tools use **`gemini-3.1-flash-lite`** (separate API quota from voice Live API).
- Config: `memory/coding_profile.json` → `coding_model`
- Voice stays on Live (`main.py`); do not change that for coding.

## Commands (run from repo root)

```bash
python -m pytest tests/ -q --tb=line
python -m ruff check actions tests agent memory core --output-format=concise
```

For exercises without lint noise: `coding_workspace` `set_workspace` with `tests_only: true`.
If `ruff` is not installed: `pip install ruff` or set `tests_only`.

## Coding rules

1. **Minimal diffs** — change only what the goal requires; do not reformat unrelated files.
2. **Match existing style** — same imports, logging (`core.logger.get_logger`), and tool registration patterns.
3. **Register new tools** via `tool_builder` (`create_module` / `create_custom`) or manually in `agent/tool_registry.py` `_ACTION_MODULES`.
4. **No secrets** — do not write keys into code, logs, or committed JSON.
5. **Tests** — add or update tests in `tests/` for behavior you change.
6. **Patch tools** — prefer unified `diff` hunks or unique `search`/`replace`; always `read` the file first.
7. **Verify** — after edits, lint + pytest must pass before calling `finish`.

## PC control (Fedora)

- **`pc_controller`** — volume, brightness, battery, focus/close windows, browser tabs, media
- Requires: `pactl` (PipeWire), `upower`, `wmctrl`, `brightnessctl`, `playerctl`
- Run once: `bash scripts/install_pc_tools_fedora.sh`
- **browser_control** = separate Playwright browser; for *your* Chrome tabs use **pc_controller** `browser_tab`

## Background / alerts (Fedora)

- `lucas_service` → `install` (systemd user unit), `enable_wake`, `status`, `snooze`
- Reminders call `scripts/lucas_alert.py` (sound, notify, trigger, optional wake)
- ICS: `memory/calendar_sync.json` → `calendar_manager` `sync_ics`

## Tool routing (for the voice assistant)

| User intent | Tool |
|-------------|------|
| Fix/explore/edit this repo (manual) | `coding_workspace` (grep, read, patch) |
| Complex coding task / swarm | `coding_swarm` (`action: task`) — Lucas repo loads `memory/lucas_swarm_brain.md` |
| Swarm stuck after CLI kill | `python scripts/swarm_cli.py recover --force` |
| New multi-file app | `coding_swarm` (`action: build`) |
| OS / apps / web / files | other `actions/*` tools |

## Agent capability (honest limits)

| Task size | Best tool | Notes |
|-----------|-----------|--------|
| Small Lucas/Lumina patch | `coding_workspace` | grep → read → patch → run |
| New app / multi-file feature | `coding_swarm` | Scout → plan → worker (Aider) → verify |
| Whole Lucas refactor | Not ready alone | Use Cursor/IDE; swarm scores ~5.5 on huge files per `memory/self_improvements.md` |
| Research / "how do I…" | `SearchAgent` + swarm research | Keys from `config/agent_keys.json` (round-robin) |

Swarm **does not spawn new autonomous agents** by itself; it runs fixed roles (scout, planner, worker, verifier). To add a new agent module, implement under `agent/` and wire into `lucas_swarm` or `tool_registry`.

## Forbidden without explicit user request

- Deleting large directories or `git` history rewriting
- `pip install` unless the task is dependency setup
- Modifying `config/api_keys.json` or user credentials
