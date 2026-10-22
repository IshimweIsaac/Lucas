# LUCAS: Voice-Controlled AI Desktop Assistant

LUCAS is a real-time voice assistant for Linux. It keeps a live WebSocket session open with the
Google Gemini Live API, streams microphone audio and the screen, and carries out what you ask by
calling tools that control the computer: windows, browser, files, settings, calendar and code.

215 Python modules, 53,000+ lines of Python, 64 test files (1,500+ tests). Built by
[Isaac Ishimwe](https://github.com/IshimweIsaac).

## How it works

```
microphone (16 kHz PCM) -> Gemini Live API (WebSocket) -> tool call -> action module -> result
                                     |
                                     v
                          spoken reply (24 kHz PCM) -> speaker
```

- `main.py` runs the live voice session and registers every tool from `agent/tool_registry.py`.
- `actions/` holds 31 action modules. Each one exposes a `TOOL_SCHEMA` and a handler.
- `core/` holds the building blocks the actions use: desktop control, audio, networking,
  notifications, the screen-grounding pipeline and the OpenCode integration.
- `agent/` holds the planner, executor, error handling, API key rotation and helper agents.
- `memory/` holds long-term memory, the session brief and model clients. Runtime data is
  written here and is gitignored.

The system prompt is assembled from long-term memory, a short session brief and the current
screen state, so a reconnect picks up where the conversation left off.

## Capabilities

- Real-time, interruptible voice conversation in the user's language
- Desktop automation: mouse, keyboard, windows, workspaces, volume, brightness, WiFi, Bluetooth
- Screen grounding to click things by name: accessibility tree, then OCR, then template
  matching, then a Gemini vision fallback
- Browser automation with Playwright
- Coding tools: repo search, reading and patching files, running tests, and multi-agent coding
  through OpenCode
- Calendar, reminders and daily routines with desktop alerts (systemd user service)
- Email, notes, habits, clipboard history and document generation
- Proactive check-ins and a Telegram bot for remote control
- Hot reload of action modules while the assistant is running

## Getting started

Requirements: Linux (developed on Fedora with Wayland), Python 3.11+, a microphone and a
Google Gemini API key.

```bash
git clone https://github.com/IshimweIsaac/Lucas.git
cd Lucas
python setup.py          # installs requirements.txt and Playwright browsers
```

Create `config/api_keys.json` (it is gitignored):

```json
{ "gemini_api_key": "YOUR_GEMINI_API_KEY" }
```

Optional: put extra keys for the coding agents in `config/agent_keys.json`, and copy
`config/google_calendar_client.json.example` to set up Google Calendar.

Run it:

```bash
python main.py
```

Optional desktop tools for full PC control on Fedora:

```bash
bash scripts/install_pc_tools_fedora.sh
```

The web UI front end is developed in a separate repository and is not included here.

## Tests

```bash
python -m pytest tests/ -q
python -m ruff check actions tests agent memory core
```

The tests mock every external API, so they run without any API keys.

## License

Personal and non-commercial use only, under
[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
