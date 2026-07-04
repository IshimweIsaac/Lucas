# 🧠 LUCAS — AI Voice-Controlled Desktop Assistant

> **A real-time, voice-controlled, autonomous AI assistant that speaks, sees, and controls your computer — powered by Google Gemini Live API.**

Lucas is a locally-run desktop AI assistant engineered for total computer autonomy. It maintains a persistent WebSocket connection to Google Gemini 3.1 Flash Live, streams real-time audio and screen video, and dispatches tool calls to 27+ action modules spanning desktop automation, coding, browser control, file management, system settings, and more.

Built by [Isaac Ishimwe](https://github.com/IshimweIsaac) — 170 Python modules, 50 test files, 12,000+ lines of production code.

---

## ✨ Demo

<!-- Screenshots and demo video to be added. -->
<!-- Voice interaction, swarm coding pipeline, and UI screenshots coming soon. -->

---

## 🎯 Key Capabilities

### 🎙️ Real-Time Voice Control
- **Gemini Live API** — WebSocket streaming with 16kHz audio input, 24kHz audio output
- Sub-second voice-to-action latency via `sounddevice` + PulseAudio
- Voice activity detection (VAD) with auto-unmute
- Voice routing guards — 12+ intent classification patterns prevent misrouted commands

### 🖥️ Desktop Automation
- **Mouse & Keyboard** — Bezier gesture paths with 5 speed modes (insane → instant), screen coordinate finding, OCR-based click targeting
- **System Control** — Volume, brightness, windows, workspaces, browser tabs, media, battery monitoring
- **Application Launch** — Open/focus any installed application
- **System Settings** — WiFi, display, power, shortcuts, user accounts, firewall, printing, Bluetooth

### 🌐 Browser & Web
- **Playwright Browser** — Full browser automation for web tasks
- **Web Search** — Tavily and DuckDuckGo integration with rich result formatting
- **YouTube** — Search and playback control

### 🤖 Multi-Agent Swarm Coding
- **Autonomous pipeline** — `planner.py` (goal decomposition) → `executor.py` (step execution with retry) → `error_handler.py` (auto-fix)
- Task classification via dedicated `task_classifier_agent.py`
- Priority-based async task queue with low/normal/high tiers
- Threaded parallel agent execution

### 👁️ Screen Vision
- **Live desktop streaming** to Gemini at ~1 FPS via MSS + OpenCV
- **Screen capture + analysis** — on-demand screenshot, template matching (`screen_find`), visual click targeting (`see_and_click`)
- Wayland support via PipeWire screencast fallback

### 🧠 3-Tier Memory System
- **Long-term memory** — 6-category JSON store (`identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes`)
- **Session brief** — 48-bullet rolling context surviving Live reconnects
- **Conversation journal** — Last 24 exchanges for cold-start recovery

### 🧩 27+ Action Tool Modules
Computer control, coding workspace, screen processing, file management, browser automation, system control, email, web search, weather, reminders, calendar, habits tracking, notes, presentations, document control, package management, Docker, network, clipboard, macros, Bluetooth, printer, extensions, and more.

### 🖼️ Dual-Mode UI
- **Web UI** — React 19 + TypeScript + Vite + Electron (in `lucas_ui/`)
- **WebSocket bridge** for real-time communication between the Python backend and web frontend

### 📱 Telegram Bot
- Remote control Lucas via Telegram (`telegram_bot.py`, 407 lines)
- Process management, command dispatch, and logging

### 📄 Document Generation
- Programmatic creation of Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), and PDF documents

### 🔄 Self-Improvement Loop
- Automatic heartbeat monitoring
- `self_improve.py` — run backlog items from `memory/self_improvements.md`
- `tool_builder.py` — runtime tool creation without code restart
- `hot_reloader.py` — source file watching + module reload

---

## 🏗️ Architecture

### Voice Pipeline

```
User speaks → Microphone (sounddevice, 16kHz PCM int16)
  → asyncio Queue (1024-byte chunks)
    → Gemini Live WebSocket (google-genai)
      → Tool dispatch via agent/tool_registry.py
        → 27+ action modules → result string
          → FunctionResponse returned to Gemini
            → Gemini speaks (24kHz PCM audio)
              → sounddevice → speakers
```

### Tool Dispatch

```
main.py → tool_registry.dispatch(name, params)
  → voice_routing.guard_tool_call()  ← 12+ intent guards
    → actions/<module>.handler(params)
      → return result string
        → Gemini Live FunctionResponse
```

### Memory Cycle

```
Long-term (JSON, 6 categories, ~2200 chars)
  → Session brief (48 bullets, ~4000 chars, survives reconnect)
    → Conversation journal (24 entries, cold-start recovery)
      → Assembled into Live connect system prompt
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.11+ (170 modules, ~12K lines) |
| **AI** | Google Gemini 3.1 Flash Live API (`google-genai`) |
| **Audio** | `sounddevice`, PulseAudio, 16/24 kHz streaming |
| **Desktop Control** | `pyautogui`, `ydotool`, `wtype` (Wayland), `wmctrl` |
| **Screen Capture** | `mss`, `opencv-python`, PipeWire (Wayland) |
| **Web UI** | React 19, TypeScript, Vite, Electron |
| **Browser** | Playwright |
| **Search** | Tavily API, DuckDuckGo (`ddgs`) |
| **Documents** | `python-pptx`, `python-docx`, `openpyxl`, `reportlab` |
| **Messaging** | `python-telegram-bot` |
| **Calendar** | Google Calendar API, ICS sync |
| **Services** | systemd user units, PipeWire |
| **Testing** | `pytest` (50 test files) |
| **Linting** | `ruff` |

---

## 📁 Project Structure

```
Lucas/
├── main.py                     # Entry point (1,060 lines) — Live session, 5 async supervisors
├── telegram_bot.py             # Telegram remote control (407 lines)
├── actions/                    # 27 tool modules — one file per capability
│   ├── coding_workspace.py     # Repo-aware grep→read→patch→verify loop (1,176 lines)
│   ├── computer_control.py     # Mouse, keyboard, gestures, screen find/click (555 lines)
│   ├── opencode_control.py     # OpenCode multi-agent integration (469 lines)
│   ├── screen_processor.py     # Screenshot capture + vision analysis (469 lines)
│   ├── web_search.py           # Tavily + DuckDuckGo search
│   ├── pc_controller.py        # Volume, brightness, windows, workspaces
│   ├── file_controller.py      # CRUD, find, disk usage
│   ├── browser_control.py      # Playwright browser automation
│   ├── calendar_manager.py     # Calendar events CRUD + ICS sync
│   ├── email_control.py        # Email sending
│   ├── presentation_control.py # Slide management
│   ├── heartbeat.py            # Periodic wake-ups + autonomy
│   ├── self_improve.py         # Self-improvement backlog runner
│   ├── tool_builder.py         # Runtime tool creation
│   ├── reminder.py             # Timed alerts
│   ├── habits_control.py       # Habit tracking
│   ├── notes_control.py        # Note management
│   ├── system_control.py       # System settings (WiFi, display, power)
│   ├── weather_report.py       # Weather lookup
│   ├── lpm_control.py          # Package management
│   └── ... (7 more)
├── agent/                      # Agent orchestration core (13 files)
│   ├── tool_registry.py        # Central dispatch — register/list/dispatch
│   ├── voice_routing.py        # Intent routing guards (12+ patterns)
│   ├── planner.py              # Goal decomposition into steps (298 lines)
│   ├── executor.py             # Step-by-step execution with retry (345 lines)
│   ├── error_handler.py        # Error analysis + auto-fix
│   ├── task_classifier_agent.py # Goal complexity classification
│   ├── task_queue.py           # Priority async task queue
│   ├── search_agent.py         # Specialized search agent
│   ├── summarizer_agent.py     # Text summarization
│   ├── health_agent.py         # System health monitoring
│   ├── key_manager.py          # API key rotation
│   └── task_history.py         # Task history tracking
├── core/                       # Shared infrastructure (51 modules)
│   ├── live_tools.py           # Tool declaration trimming for Live API
│   ├── prompt.txt              # System prompt (50 lines)
│   ├── pc_control.py           # Low-level PC control (PulseAudio, brightness)
│   ├── input_control.py        # Low-level input (ydotool, wtype)
│   ├── window_list.py          # X11/Wayland window listing
│   ├── websocket_server.py     # WebSocket bridge for web UI
│   ├── heartbeat.py            # Heartbeat automation
│   ├── logger.py               # Structured logging
│   ├── hot_reloader.py         # Source file watcher + module reload
│   ├── path_utils.py           # Path resolution utilities
│   ├── system_clock.py         # Time/date formatting
│   ├── platform.py             # Platform detection
│   ├── systemd_service.py      # systemd user service management
│   ├── opencode/               # OpenCode integration (16 files)
│   ├── screen/                 # Screen capture & streaming
│   ├── calendar/               # Calendar backend (Google, ICS)
│   ├── document/               # Document generation
│   ├── github/                 # GitHub integration
│   └── ... (30+ more utilities)
├── lucas_ui/                   # Web UI (React 19 + TypeScript + Vite + Electron)
├── memory/                     # Persistence & memory (40 entries)
│   ├── memory_manager.py       # Long-term JSON CRUD
│   ├── session_brief.py        # Rolling session brief
│   ├── conversation_journal.py # Last 24 exchanges
│   ├── config_manager.py       # API key & base directory config
│   └── *.json                  # State files
├── tests/                      # 50 test files — pytest
├── config/                     # API keys (gitignored)
├── scripts/                    # Utility scripts
└── setup.py                    # First-time setup (pip install + playwright)
```

---

## 🚀 Getting Started

### Prerequisites

- **OS:** Linux (Fedora, Ubuntu, Arch), macOS, or Windows
- **Python:** 3.11 or 3.12
- **Microphone:** Required for voice interaction
- **API Key:** Google Gemini API key (free tier available)

### Quick Start

```bash
# Clone
git clone https://github.com/IshimweIsaac/Lucas.git
cd Lucas

# Install dependencies
python setup.py   # pip install -r requirements.txt + playwright install

# Run (web UI mode)
python main.py

# Run with Electron UI
python main.py --ui-mode qt
```

### Fedora — Background Alerts

For wake-on-alert, systemd user service, and reminder deduplication:

```bash
python -c "from actions.lucas_service import lucas_service; print(lucas_service({'action': 'setup'}))"
```

### Run Tests

```bash
pytest tests/ -x --tb=line
```

---

## 🧪 Testing

- **50 test files** covering action modules, agent logic, and core utilities
- Predictable patterns — each source module has a corresponding `test_<module>.py`
- Mock Gemini API and audio — no external dependencies required during CI

---

## 🧩 Key Modules (Highlights)

### `actions/coding_workspace.py` (1,176 lines)
Advanced repo-aware coding agent with a complete grep → read → patch → verify loop. Supports terminal execution, directory listing, workspace management, and anti-wipe protections. Session tree cache with 300s TTL.

### `agent/planner.py` + `agent/executor.py`
Goal decomposition engine that breaks user requests into step-by-step plans (max 5 steps) and executes them through the tool registry with automatic retry (max 2 per step) and error analysis.

### `agent/voice_routing.py`
Intent routing guard that catches 12+ common misroutings — window management, terminal commands, screen analysis, time/date queries, and OpenCode echo-loop detection — redirecting them to the correct tool before execution.

### `actions/opencode_control.py` (469 lines)
Integration with the OpenCode multi-subagent AI coding system. 33 actions covering message dispatch, chat sessions, job management, window control, file exploration, and more. Dedup logic prevents redundant sends.

### `actions/computer_control.py` (555 lines)
Full desktop automation: move, glide, nudge, click, drag, swipe, hover, scroll, type, hotkey, copy, paste, screenshot, screen find, screen click, see-and-click, cursor sync, window focus. Bezier mouse paths with 5 speed profiles.

---

## 👤 Author

**Isaac Ishimwe**

[![GitHub](https://img.shields.io/badge/GitHub-IshimweIsaac-181717?style=flat-square&logo=github)](https://github.com/IshimweIsaac)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Isaac%20Ishimwe-0A66C2?style=flat-square&logo=linkedin)](https://linkedin.com/in/ishimwe-isaac)
[![Email](https://img.shields.io/badge/Email-ishimwe.isaac%40example.com-EA4335?style=flat-square&logo=gmail)](mailto:ishimwe.isaac@example.com)

Kigali, Rwanda

---

## 📄 License

Personal and non-commercial use only.
Licensed under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

---

> **Built with Python, Google Gemini, and a lot of caffeine.**  
> Questions? Open an issue or reach out on [GitHub](https://github.com/IshimweIsaac/Lucas).
