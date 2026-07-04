# LUCAS : Voice-Controlled AI Desktop Assistant

Real-time voice-controlled AI assistant for Linux. Maintains a persistent
WebSocket connection to Google Gemini 3.1 Flash Live, streams audio and screen
video, and dispatches tool calls to 35+ action modules.

42,724 lines of Python. 50 test files. Built by Isaac Ishimwe.

:-

## Architecture

Voice pipeline: User -> microphone (16kHz PCM) -> Gemini Live API WebSocket ->
tool dispatch -> audio response (24kHz PCM) -> speaker.

System prompt assembles context from 3-tier memory (long-term, session brief,
conversation journal) plus screen state and heartbeat status.

:-

## Capabilities

- Real-time voice interaction with ~500ms latency
- Desktop automation: mouse, keyboard, windows, workspaces, volume, brightness
- Browser control via Playwright
- Multi-agent swarm coding pipeline: scout -> research -> plan -> execute -> verify
- Live desktop streaming to Gemini at ~1 FPS via MSS/OpenCV
- Screen vision analysis (screenshot capture + Gemini vision)
- 18 specialized learning agents (summarizer, tutor, quiz engine, etc.)
- GitHub/git workflow automation with Conventional Commits
- Document generation: Word, Excel, PowerPoint, PDF
- 3-tier memory system with automatic context assembly
- Telegram bot interface for remote control
- Hot-reloader for live code updates

:-

## Stack

- Python 3.11+, Google Gemini Live API (gemini-3.1-flash-live-preview)
- Audio: sounddevice, PulseAudio, 16kHz/24kHz PCM
- Desktop: pyautogui, OpenCV, MSS, ydotool, wtype
- UI: PyQt6 (31+ windows), React/Electron (web UI)
- Browser: Playwright
- AI: Gemini Pro/Flash for text, Gemini Live for voice
- Memory: JSON-based 3-tier system
- Integrations: GitHub CLI, Telegram Bot API, Google Calendar
- Services: systemd, PipeWire

## Development Tools

Cursor, Claude Code, Windsurf, OpenCode, VS Code, Git, pytest, Ruff

:-

github.com/IshimweIsaac/Lucas
