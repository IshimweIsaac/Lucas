import asyncio
import atexit
import re
import sys
import threading
import json
import traceback
from pathlib import Path
from typing import Any, Coroutine

from core.alert_delivery import clear_pid_file, enforce_single_instance, write_pid_file
from core.live_tools import trim_tools
from core.logger import get_logger
from core.websocket_server import WebSocketPlayer, WebSocketServer

# OpenCode integration
from core.opencode.opencode_server import ensure_server as _oc_ensure_server  # noqa: F401
from core.opencode.opencode_defaults import DEFAULT_AGENT as _OC_DEFAULT_AGENT  # noqa: F401

logger = get_logger(__name__)

import sounddevice as sd
from google import genai
from google.genai import types
from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
)
from memory import session_brief
from memory.config_manager import (
    get_base_dir,
    get_gemini_key as _get_api_key,
    get_setting,
)


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL = "models/gemini-3.1-flash-live-preview"
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are LUCAS, a localized intelligent AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

_MIN_REMEMBER_CHARS = 60

_BG_TASKS: set[asyncio.Task] = set()
_BG_MAX_TRACKED: int = 64          # warn-only threshold, not a hard cap
_BG_BACKLOG_WARNED = False         # one-shot flag; reset once count drops back below


def _remember_exchange(user_text: str, assistant_text: str) -> None:
    """Fire-and-forget storage of one exchange in semantic memory."""
    try:
        from memory import semantic_memory

        semantic_memory.remember(
            f"User said: {user_text}\nLucas replied: {assistant_text}",
            kind="conversation",
        )
    except Exception as e:
        logger.warning("Semantic remember failed: %s", e)


def _bg_task_done(task: asyncio.Task) -> None:
    """Discard a finished task; log unexpected exceptions. Never raises."""
    global _BG_BACKLOG_WARNED
    _BG_TASKS.discard(task)
    if len(_BG_TASKS) < _BG_MAX_TRACKED:
        _BG_BACKLOG_WARNED = False
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return  # cancelled tasks have nothing to report
    if exc is not None:
        logger.warning("bg task failed: %s", exc)


def _spawn_bg(coro: Coroutine[Any, Any, Any]) -> None:
    """Create a task, keep a strong reference until done, log exceptions."""
    global _BG_BACKLOG_WARNED
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError as e:
        logger.warning("bg spawn skipped (no running loop): %s", e)
        coro.close()
        return
    _BG_TASKS.add(task)
    if len(_BG_TASKS) >= _BG_MAX_TRACKED and not _BG_BACKLOG_WARNED:
        _BG_BACKLOG_WARNED = True
        logger.warning("bg backlog: %d pending memory writes", len(_BG_TASKS))
    task.add_done_callback(_bg_task_done)


def _build_recall_context() -> str:
    """Recall semantic memories relevant to the current session topic."""
    try:
        from memory import semantic_memory

        topic = session_brief.load_brief().get("topic", "")
        if not topic:
            return ""
        return semantic_memory.format_recall_for_prompt(topic)
    except Exception as e:
        logger.warning("Semantic recall failed: %s", e)
        return ""


def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


import agent.tool_registry as tool_registry

SYSTEM_TOOLS = [
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {
                    "type": "STRING",
                    "description": "Complete description of what to accomplish",
                },
                "priority": {
                    "type": "STRING",
                    "description": "low | normal | high (default: normal)",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "shutdown_lucas",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Lucas. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "restart_lucas",
        "description": (
            "Restarts the Lucas assistant app immediately (reload UI and tools). "
            "Call when the user says restart, reboot Lucas, restart yourself, "
            "or restart the assistant — in ANY language. "
            "Do NOT use for rebooting the whole computer (use computer_settings "
            "restart only if they explicitly mean the PC)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "mute_microphone",
        "description": (
            "Mute the user's microphone in the Lucas UI. "
            "Call this ONLY when the user explicitly asks you to 'mute me', 'stop listening', or 'mute the microphone'. "
            "Do NOT use pc_controller mute for this! pc_controller mute mutes the OS speakers (which mutes you). "
            "This tool mutes the microphone input to save bandwidth."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "read_memory",
        "description": (
            "Read all saved memory about the user. Call at session start to refresh knowledge "
            "of who the user is, their preferences, projects, relationships, and notes. "
            "Returns everything currently stored in long-term memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    ),
                },
                "key": {
                    "type": "STRING",
                    "description": "Short snake_case key (e.g. name, favorite_food, sister_name)",
                },
                "value": {
                    "type": "STRING",
                    "description": "Concise value in English (e.g. Fatih, pizza, older sister)",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
]


def _tool_declarations() -> list[dict]:
    """Fresh list on each Live connect so new tools appear after reconnect."""
    return trim_tools(tool_registry.get_schemas()) + SYSTEM_TOOLS


class LucasLive:
    def __init__(self, ui: WebSocketPlayer):
        self.ui = ui
        self.session = None
        self.audio_in_queue = None
        self.out_queue = None
        self._loop = None
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._disconnect = threading.Event()
        self._input_stream = None  # sd.InputStream  (mic)
        self._output_stream = None  # sd.RawOutputStream (speaker)
        import time

        self._last_speech_time = time.time()
        # VAD (voice activity detection) state for auto-unmute
        self._vad_consecutive = 0  # consecutive loud frames
        self._vad_threshold = get_setting(
            "vad_threshold", 600
        )  # RMS energy threshold (int16 range) — lower = more sensitive
        self._vad_frames_needed = (
            2  # consecutive loud frames to trigger unmute (2 = very fast)
        )

        # OpenCode inject state
        self._pending_opencode_inject: list[tuple[str, str]] = []
        self._opencode_last_injected = ""
        self._opencode_inject_pending = False
        self._opencode_inject_lock = threading.Lock()
        self._away_summary: list[dict] = []

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": text}]}], turn_complete=True
            ),
            self._loop,
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _wire_opencode_background(self) -> None:
        """Wire OpenCode background handlers to the Live session."""
        try:
            from core.opencode.opencode_background import (
                set_reply_handler,
                set_stream_handler,
                set_completion_handler,
            )
            from core.opencode.opencode_trace import set_trace_handler

            set_reply_handler(self._on_opencode_reply)
            set_stream_handler(self._on_opencode_stream)
            set_completion_handler(self._on_opencode_complete)
            set_trace_handler(self._on_opencode_trace)
        except Exception as e:
            logger.warning("OpenCode background wiring failed: %s", e)

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": text}]}], turn_complete=True
            ),
            self._loop,
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _inject_opencode_to_live(
        self, reply: str, label: str = "OPENCODE SAYS"
    ) -> None:
        """Inject OpenCode reply into the Live session so Gemini speaks it."""
        if not self._loop or not self.session:
            return
        with self._opencode_inject_lock:
            if self._opencode_inject_pending:
                return
            self._opencode_inject_pending = True
            self._opencode_last_injected = reply

        text = f"{label}: {reply}\n\nSpeak the above to the user right now. Clearly attribute it to OpenCode."
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": text}]}],
                turn_complete=True,
            ),
            self._loop,
        )

    def _on_opencode_reply(self, reply: str, final: bool, meta: dict) -> None:
        """Handle interim OpenCode reply (from ReplyRelay)."""
        self.ui.write_log(f"OC: {reply[:80]}")

    def _on_opencode_stream(self, reply: str, final: bool, meta: dict) -> None:
        """Handle streaming OpenCode reply — inject incremental text."""
        if not final:
            return
        self._inject_opencode_to_live(reply, "OPENCODE SAYS[stream]")

    def _on_opencode_complete(self, text: str, meta: dict) -> None:
        """Handle completed OpenCode job — inject final reply."""
        # Clear inject pending
        with self._opencode_inject_lock:
            self._opencode_inject_pending = False

        # Check if user is present
        # Always inject — user is present or will hear on reconnect
        if True:
            self._inject_opencode_to_live(text, "OPENCODE SAYS")
            self.ui.write_log(f"OC DONE: {text[:200]}")
        else:
            # Queue for away summary
            self._away_summary.append(
                {
                    "action": meta.get("action", "task"),
                    "goal": meta.get("goal", "")[:200],
                    "reply": text[:500],
                    "session_id": meta.get("session_id", ""),
                }
            )
            # Telegram notification
            try:
                from telegram_bot import send_opencode_notification

                send_opencode_notification(
                    goal=meta.get("goal", ""),
                    reply_preview=text[:400],
                    job_token=meta.get("token", ""),
                )
            except Exception as e:
                logger.warning("Telegram notification failed: %s", e)

    def _on_opencode_trace(self, digest: str) -> None:
        """Handle trace digest — pin to session brief."""
        try:
            from memory import session_brief

            session_brief.pin_opencode_trace(digest)
        except Exception as e:
            logger.warning("Failed to pin opencode trace: %s", e)

    def _build_config(self, recall_ctx: str = "") -> types.LiveConnectConfig:
        from core.system_clock import format_connect_banner

        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        time_str = format_connect_banner()
        time_ctx = (
            f"[CURRENT DATE & TIME — stale after connect]\n"
            f"At session connect it was: {time_str}\n"
            f"When the user asks for the time or date, you MUST call pc_controller "
            f"(action=time or action=date) and speak that tool result — never guess "
            f"from this block or from session brief.\n"
            f"Use the tool result for reminder scheduling math.\n\n"
        )

        brief_str = session_brief.format_for_prompt()

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        if brief_str:
            parts.append(brief_str)
        if recall_ctx:
            parts.append(recall_ctx)
        parts.append(sys_prompt)

        # Append OpenCode prompt section
        try:
            from core.opencode.opencode_orchestration import format_live_prompt_section

            oc_section = format_live_prompt_section()
            if oc_section:
                parts.append(oc_section)
        except Exception as e:
            logger.warning("OpenCode prompt section failed: %s", e)

        # Append proactive persona/thoughts section
        try:
            from core.proactive.prompt_sections import format_proactive_section

            proactive_section = format_proactive_section()
            if proactive_section:
                parts.append(proactive_section)
        except Exception as e:
            logger.warning("Proactive prompt section failed: %s", e)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": _tool_declarations()}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[LUCAS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        from agent.voice_routing import guard_tool_call

        routed = guard_tool_call(name, args)
        if routed:
            print(f"[LUCAS] ↪️ routing guard: {routed[:80]}")
            self.ui.write_log(f"GUARD: {name}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": routed},
            )

        # Block new tool calls during OPENCODE SAYS inject
        with self._opencode_inject_lock:
            inject_blocked = self._opencode_inject_pending
        if inject_blocked and name != "opencode_control":
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={
                    "result": "BLOCKED: OPENCODE SAYS inject in progress — speak the relay only, no tools.",
                    "silent": True,
                },
            )

        from core.path_utils import normalize_tool_paths

        args, path_block = normalize_tool_paths(name, args)
        if path_block:
            print(f"[LUCAS] ↪️ path guard: {path_block[:80]}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": path_block},
            )

        if name == "read_memory":
            from memory.memory_manager import (
                load_memory,
                format_memory_for_prompt as _fmt_mem,
            )

            mem = load_memory()
            mem_str = _fmt_mem(mem)
            result = mem_str or "No saved memory found."
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": result},
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": "ok", "silent": True}
            )

        result = await self._handle_tool_inner(name, args)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[LUCAS] 📤 {name} → {str(result)[:80]}")
        try:
            session_brief.note_tool(name, str(result), args)
        except Exception as e:
            logger.warning("SessionBrief note_tool failed: %s", e)

        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _handle_tool_inner(self, name: str, args: dict) -> str:
        """Execute a tool call and return the result string.

        Handles system tools (agent_task, shutdown_lucas, restart_lucas,
        mute_microphone) and registered action tools via tool_registry.
        Error handling is included — exceptions produce error result strings.
        """
        loop = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority

                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }
                priority = priority_map.get(
                    args.get("priority", "normal").lower(), TaskPriority.NORMAL
                )
                task_id = get_queue().submit(
                    goal=args.get("goal", ""), priority=priority, speak=self.speak
                )
                result = f"Task started (ID: {task_id})."

            elif name == "shutdown_lucas":
                session_brief.clear_brief()
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")

                def _shutdown():
                    import time
                    import os

                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
                result = "Shutting down."

            elif name == "restart_lucas":
                from core.alert_delivery import restart_lucas as do_restart

                self.ui.write_log("SYS: Restart requested.")
                self.speak("Restarting now, sir.")

                def _restart():
                    import os
                    import time

                    do_restart()
                    time.sleep(0.6)
                    os._exit(0)

                threading.Thread(target=_restart, daemon=True).start()
                result = "Restarting."

            elif name == "mute_microphone":
                self.ui.muted = True
                self.ui.write_log("SYS: Microphone muted via voice command.")
                self.speak(
                    "Microphone muted. Just start speaking and I will hear you automatically."
                )
                result = "Microphone muted. Auto-unmute via VAD is active — the user can just start talking."

            elif tool_registry.has_tool(name):

                def _run_tool():
                    return tool_registry.dispatch(
                        name, parameters=args, player=self.ui, speak=self.speak
                    )

                if name == "screen_process":
                    threading.Thread(target=_run_tool, daemon=True).start()
                    result = "Vision module activated. Stay completely silent — vision module will speak directly."
                else:
                    r = await loop.run_in_executor(None, _run_tool)
                    result = r or "Done."

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Drain pending OpenCode inject after tool completes
        try:
            if self._pending_opencode_inject:
                pending = self._pending_opencode_inject.pop(0)
                self._inject_opencode_to_live(*pending)
        except Exception as e:
            logger.warning("Failed to drain opencode inject: %s", e)

        return result

    def _mark_disconnected(self, reason: str) -> None:
        if not self._disconnect.is_set():
            print(f"[LUCAS] 🔌 Session dead: {reason}")
            self.ui.write_log("SYS: Connection lost — reconnecting…")
            self._disconnect.set()

    def _enqueue_out_audio(self, item: dict) -> None:
        """Drop oldest mic chunk if the send queue is full (reconnect / backpressure)."""
        q = self.out_queue
        if q is None:
            return
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass

    async def _send_realtime(self):
        while not self._disconnect.is_set():
            msg = await self.out_queue.get()
            if self._disconnect.is_set():
                break
            try:
                await asyncio.wait_for(
                    self.session.send_realtime_input(audio=msg),
                    timeout=8.0,
                )
            except Exception as e:
                self._mark_disconnected(str(e)[:80])
                break

    async def _listen_audio(self):
        print("[LUCAS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        import array as _array
        import math as _math

        def _fast_rms(raw: bytes) -> int:
            """RMS of int16 PCM without numpy — safe for PortAudio callbacks."""
            samples = _array.array("h", raw)  # zero-copy int16 view
            n = len(samples)
            if n == 0:
                return 0
            acc = 0
            for s in samples:
                acc += s * s
            return int(_math.isqrt(acc // n))

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                lucas_speaking = self._is_speaking

            raw = indata.tobytes()

            if self.ui.muted and not lucas_speaking:
                # Local VAD: check audio energy to auto-unmute
                rms = _fast_rms(raw)
                if rms > self._vad_threshold:
                    self._vad_consecutive += 1
                    if self._vad_consecutive >= self._vad_frames_needed:
                        # Speech detected — auto-unmute!
                        self.ui.muted = False
                        self._vad_consecutive = 0
                        import time

                        self._last_speech_time = time.time()
                        print(
                            f"[LUCAS] 🎤 Auto-unmuted (VAD detected speech, RMS={rms})"
                        )
                else:
                    self._vad_consecutive = 0
                return  # don't send audio while still muted

            if not lucas_speaking and not self.ui.muted:
                self._vad_consecutive = 0  # reset when actively streaming
                loop.call_soon_threadsafe(
                    self._enqueue_out_audio,
                    {"data": raw, "mime_type": "audio/pcm"},
                )

        try:
            self._input_stream = sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            )
            self._input_stream.start()
            print("[LUCAS] 🎤 Mic stream open")
            while not self._disconnect.is_set():
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Mic stream error: %s", e)
            raise
        finally:
            self._close_input_stream()

    async def _send_tool_responses(self, fn_responses) -> None:
        if self._disconnect.is_set() or not self.session:
            return
        try:
            await asyncio.wait_for(
                self.session.send_tool_response(function_responses=fn_responses),
                timeout=10.0,
            )
        except Exception as e:
            self._mark_disconnected(f"send_tool_response: {e}")

    async def _receive_audio(self):
        print("[LUCAS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while not self._disconnect.is_set():
                async for response in self.session.receive():
                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                import time

                                self._last_speech_time = time.time()
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Lucas: {full_out}")
                            out_buf = []

                            try:
                                session_brief.note_turn(full_in, full_out)
                            except Exception as e:
                                logger.warning("SessionBrief note_turn failed: %s", e)

                            if len(full_in) >= _MIN_REMEMBER_CHARS:
                                # _spawn_bg: single sanctioned fire-and-forget write path (bare create_task gets GC'd).
                                _spawn_bg(
                                    asyncio.to_thread(
                                        _remember_exchange, full_in, full_out
                                    )
                                )

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[LUCAS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self._send_tool_responses(fn_responses)
                    if self._disconnect.is_set():
                        break
        except Exception as e:
            logger.error("Receive error: %s", e)
            traceback.print_exc()
            try:
                session_brief.add_bullet(
                    f"Connection dropped ({str(e)[:60]}); reconnecting."
                )
            except Exception as exc:
                logger.warning("Failed to record disconnect bullet: %s", exc)
            self._mark_disconnected(str(e)[:80])
            raise

    async def _play_audio(self):
        print("[LUCAS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        self._output_stream = stream

        try:
            while not self._disconnect.is_set():
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            logger.error("Playback error: %s", e)
            raise
        finally:
            self.set_speaking(False)
            self._close_output_stream()

    async def _watch_triggers(self):
        trigger_dir = Path.home() / ".lucas" / "triggers"
        trigger_dir.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                for trigger_file in trigger_dir.glob("trigger_*.json"):
                    try:
                        text = await asyncio.to_thread(
                            trigger_file.read_text, encoding="utf-8"
                        )
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError as e:
                            try:
                                data, _ = json.JSONDecoder().raw_decode(text.lstrip())
                                logger.warning(
                                    "Recovered partial JSON from corrupted trigger %s: %s",
                                    trigger_file,
                                    e,
                                )
                            except Exception:
                                logger.warning(
                                    "Removing unparseable trigger %s: %s",
                                    trigger_file,
                                    e,
                                )
                                await asyncio.to_thread(
                                    trigger_file.unlink, missing_ok=True
                                )
                                continue
                        message = data.get("message", "")
                        if message and self.session:
                            prompt = f"[SYSTEM REMINDER TRIGGERED]: {message}. Treat this as a direct command from the user and act on it immediately."
                            print(f"[LUCAS] ⏰ Trigger found: {message}")
                            await self.session.send_client_content(
                                turns=[{"role": "user", "parts": [{"text": prompt}]}],
                                turn_complete=True,
                            )
                        await asyncio.to_thread(trigger_file.unlink, missing_ok=True)
                    except Exception as e:
                        logger.warning(
                            "Error processing trigger %s: %s", trigger_file, e
                        )
            except Exception as exc:
                logger.warning("Trigger watch iteration failed: %s", exc)
            await asyncio.sleep(2)

    async def _heartbeat_loop(self):
        from core import heartbeat as hb

        cfg = await asyncio.to_thread(hb.load_config)
        while not self._disconnect.is_set():
            try:
                cfg = await asyncio.to_thread(hb.load_config)
                if cfg.get("enabled", True) and hb.should_run(cfg) and self.session:
                    prompt = await asyncio.to_thread(hb.build_wakeup_prompt, cfg)
                    if prompt:
                        print("[LUCAS] 💓 Heartbeat check")
                        self.ui.write_log("SYS: Heartbeat check")
                        await self.session.send_client_content(
                            turns=[{"role": "user", "parts": [{"text": prompt}]}],
                            turn_complete=True,
                        )
                        await asyncio.to_thread(hb.mark_run, cfg)

                    # Check for OpenCode away summary to inject
                    if self._away_summary:
                        try:
                            if True:  # Always inject away summary when user returns
                                parts = [
                                    "SUMMARY WHILE YOU WERE AWAY — OpenCode completed tasks"
                                ]
                                for item in self._away_summary:
                                    parts.append(
                                        f"- {item['action']}: {item['goal'][:100]}"
                                    )
                                    if item.get("reply"):
                                        parts.append(f"  Result: {item['reply'][:200]}")
                                parts.append(
                                    "Speak the above to the user right now. Say 'While you were away, OpenCode completed X tasks...'"
                                )
                                summary = "\n".join(parts)
                                await self.session.send_client_content(
                                    turns=[
                                        {"role": "user", "parts": [{"text": summary}]}
                                    ],
                                    turn_complete=True,
                                )
                                self._away_summary.clear()
                        except Exception as e:
                            logger.warning("Away summary inject failed: %s", e)
            except Exception as e:
                logger.warning("Heartbeat check failed: %s", e)
            await asyncio.sleep(hb.poll_interval_seconds(cfg))

    async def _proactive_loop(self):
        from core import proactive

        cfg = await asyncio.to_thread(proactive.config.load_config)
        while not self._disconnect.is_set():
            try:
                cfg = await asyncio.to_thread(proactive.config.load_config)
                if cfg.get("enabled", True) and self.session:
                    card = await proactive.run(
                        muted=self.ui.muted, session_ok=bool(self.session)
                    )
                    if card and card.get("deliver"):
                        title = card.get("title") or "proactive note"
                        body = card.get("body") or title
                        self.ui.write_log(f"PROACTIVE: {title[:120]}")
                        prompt = (
                            f"[LUCAS PROACTIVE]\n{body}\n\n"
                            "Share this with the user naturally, as a curious observation "
                            "or question. Keep it to ONE concise item, at most 3 sentences, "
                            "framed as 'may I share' / 'may I ask'. Always address the user "
                            "as 'sir'. Never override the user's current task."
                        )
                        await self.session.send_client_content(
                            turns=[{"role": "user", "parts": [{"text": prompt}]}],
                            turn_complete=True,
                        )
            except Exception as e:
                logger.warning("Proactive loop failed: %s", e)
            await asyncio.sleep(cfg.get("poll_interval_sec", 900))

    async def _auto_mute_loop(self):
        import time

        while not self._disconnect.is_set():
            await asyncio.sleep(5)
            if self.ui.muted:
                self._last_speech_time = time.time()
            else:
                if time.time() - self._last_speech_time > 30:
                    self.ui.muted = True
                    self.ui.write_log("SYS: Auto-muted due to 30s inactivity")
                    print("[LUCAS] 🔇 Auto-muted due to 30s inactivity")

    def _close_input_stream(self):
        """Close mic stream safely — must happen before output stream."""
        stream = self._input_stream
        self._input_stream = None
        if stream is not None:
            try:
                stream.stop(ignore_errors=True)
                stream.close()
            except Exception as e:
                logger.warning("Mic stream close error: %s", e)

    def _close_output_stream(self):
        """Close speaker stream safely — must happen after input stream."""
        stream = self._output_stream
        self._output_stream = None
        if stream is not None:
            try:
                stream.stop(ignore_errors=True)
                stream.close()
            except Exception as e:
                logger.warning("Speaker stream close error: %s", e)

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(), http_options={"api_version": "v1beta"}
        )

        reconnect_delay = 1

        while True:
            try:
                print("[LUCAS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                self._disconnect.clear()
                session_brief.note_reconnect()

                # Ensure OpenCode server is running
                try:
                    from core.opencode.opencode_server import (
                        ensure_server as _oc_ensure,
                    )

                    _oc_ensure(BASE_DIR)
                except Exception as e:
                    logger.warning("OpenCode server start failed: %s", e)

                recall_ctx = await asyncio.to_thread(_build_recall_context)
                config = self._build_config(recall_ctx=recall_ctx)

                try:
                    async with (
                        client.aio.live.connect(
                            model=LIVE_MODEL, config=config
                        ) as session,
                        asyncio.TaskGroup() as tg,
                    ):
                        self.session = session
                        self._loop = asyncio.get_event_loop()

                        # Wire OpenCode background handlers
                        self._wire_opencode_background()

                        self.audio_in_queue = asyncio.Queue()
                        self.out_queue = asyncio.Queue(maxsize=10)
                        self._turn_done_event = asyncio.Event()

                        print("[LUCAS] ✅ Connected.")
                        reconnect_delay = 1  # Reset backoff on successful connect
                        from agent.voice_routing import default_coding_workspace
                        from core import presence_status

                        session_brief.ensure_default_workspace(
                            default_coding_workspace()
                        )
                        self.ui.set_state("LISTENING")
                        self.ui.write_log("SYS: LUCAS online.")
                        self.ui.write_log(
                            f"SYS: presence {presence_status.format_short()}"
                        )

                        tg.create_task(self._send_realtime())
                        tg.create_task(self._listen_audio())
                        tg.create_task(self._receive_audio())
                        tg.create_task(self._play_audio())
                        tg.create_task(self._watch_triggers())
                        tg.create_task(self._heartbeat_loop())
                        tg.create_task(self._proactive_loop())
                        tg.create_task(self._auto_mute_loop())
                except* Exception as eg:
                    for exc in eg.exceptions:
                        if not isinstance(exc, asyncio.CancelledError):
                            print(f"[LUCAS] ⚠️ Task: {exc}")

            except Exception as e:
                logger.error("Session error: %s", e)
                traceback.print_exc()
            finally:
                self.session = None
                self.set_speaking(False)
                # Close audio streams sequentially to avoid PortAudio double-free
                self._close_input_stream()
                self._close_output_stream()
                self.ui.set_state("THINKING")
            print(f"[LUCAS] 🔄 Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


def main():
    # Single-instance guard: kills a stale live instance (or refuses with
    # LUCAS_REFUSE_SECOND=1) before we start the Live session / telegram / audio.
    enforce_single_instance()
    write_pid_file()
    atexit.register(clear_pid_file)

    import argparse

    parser = argparse.ArgumentParser(description="LUCAS")
    parser.add_argument("--ui-mode", default="web", choices=["web", "qt"])
    args = parser.parse_args()

    if args.ui_mode == "qt":
        print("[LUCAS] PyQt6 UI mode is deprecated. Use --ui-mode=web. Exiting.")
        sys.exit(1)

    from core.websocket_server import WS_PORT as _WS_PORT

    ws_server = WebSocketServer(host="localhost", port=_WS_PORT)
    player = WebSocketPlayer(ws_server)

    def runner():
        player.wait_for_api_key()

        # Hot-reloader for development — watches actions/, core/, agent/
        try:
            from core.hot_reloader import start as start_hot_reloader

            start_hot_reloader()
        except Exception as e:
            logger.warning("Failed to start hot-reloader: %s", e)

        try:
            import telegram_bot

            telegram_bot.start_in_background()
        except Exception as e:
            logger.warning("Failed to start Telegram bot: %s", e)

        async def _run():
            await ws_server.start()
            lucas = LucasLive(player)
            await lucas.run()

        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()

    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🔴 Shutting down...")


if __name__ == "__main__":
    main()
