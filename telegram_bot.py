import asyncio
import atexit
import os
import platform
import subprocess
import sys
import logging
import threading
from pathlib import Path

import psutil
import requests

from core.logger import get_logger


# Set up logging matching the styling guidelines
logger = get_logger(__name__)

# Suppress verbose telegram polling error tracebacks (non-fatal Conflict/NetworkError)
class _TelegramErrorFilter(logging.Filter):
    """Filter out verbose tracebacks from telegram polling errors."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(x in msg for x in (
            "Exception happened while polling",
            "Conflict: terminated by other getUpdates",
            "Temporary failure in name resolution",
        )):
            return False
        return True

# Apply filter to telegram and httpx loggers
for _name in ("telegram", "httpx", "httpcore"):
    _log = logging.getLogger(_name)
    _log.addFilter(_TelegramErrorFilter())
    _log.setLevel(logging.WARNING)

try:
    from telegram import Update
    from telegram.error import Conflict, NetworkError, TimedOut
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False

from memory.config_manager import get_telegram_token, get_telegram_allowed_users  # noqa: E402


class TelegramSpeechCollector:
    def __init__(self):
        self.texts = []

    def __call__(self, text: str):
        self.texts.append(text)
        logger.info(f"[Telegram Speech] {text}")

    def get_full_speech(self) -> str:
        return " ".join(self.texts).strip()


def check_authorized(user_id: int) -> bool:
    allowed = get_telegram_allowed_users()
    if not allowed:
        # If no users are allowed yet, we log the user_id so they can add it to their config,
        # but we don't allow execution for security reasons.
        logger.warning(f"No allowed users configured. Request from user ID: {user_id}")
        return False
    return user_id in allowed


def _send_telegram(text: str) -> bool:
    """Send a plain text message via the Telegram Bot HTTP API.

    Returns True on success, False on failure.
    """
    token = get_telegram_token()
    if not token:
        logger.warning("Telegram token not configured — cannot send message.")
        return False

    users = get_telegram_allowed_users()
    if not users:
        logger.warning("No allowed Telegram users configured — cannot send message.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": users[0], "text": text, "parse_mode": "HTML"}

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.debug(f"Telegram message sent to user {users[0]}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def send_opencode_notification(
    goal: str, reply_preview: str = "", job_token: str = ""
) -> None:
    """Send a Telegram notification when an OpenCode job completes while user is away."""
    text = (
        f"\U0001f916 OpenCode Complete\n\n"
        f"Task: {goal[:200]}\n"
        f"Result: {reply_preview[:400]}\n"
    )
    if job_token:
        text += f"Job: {job_token[-10:]}"
    try:
        _send_telegram(text)
    except Exception as e:
        print(f"[Telegram] Failed to send opencode notification: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Sir"

    if check_authorized(user_id):
        await update.message.reply_text(
            f"Greetings, {username}. Lucas Telegram Bot interface is online and ready.\n"
            "You are authorized. Send me any command or query."
        )
    else:
        await update.message.reply_text(
            f"Hello. You are not authorized to control this Lucas instance.\n"
            f"Your Telegram User ID is: `{user_id}`\n\n"
            "Please add this ID to the `telegram_allowed_users` list in your `config/api_keys.json` file."
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_authorized(user_id):
        await update.message.reply_text("Unauthorized.")
        return

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    active_window = "Unknown"

    try:
        if platform.system() == "Linux":
            res = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                active_window = res.stdout.strip()
    except Exception:
        pass

    status_msg = (
        "📈 *Lucas Host Status*\n"
        f"🖥️ OS: {platform.system()}\n"
        f"⚙️ CPU: {cpu}%\n"
        f"🧹 RAM: {ram}%\n"
        f"🖼️ Active Window: {active_window}"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")


# Global chat session cache
chat_session = None


def get_chat_session():
    global chat_session
    if chat_session is not None:
        return chat_session

    from memory.memory_manager import load_memory, format_memory_for_prompt
    from main import _load_system_prompt, _tool_declarations
    from core.system_clock import format_connect_banner
    from memory import session_brief
    from google.genai import types
    from memory.config_manager import get_genai_client

    client = get_genai_client()
    memory = load_memory()
    mem_str = format_memory_for_prompt(memory)
    sys_prompt = _load_system_prompt()
    time_str = format_connect_banner()
    time_ctx = (
        f"[CURRENT DATE & TIME — stale after connect]\n"
        f"At session connect it was: {time_str}\n"
        f"When the user asks for the time or date, you MUST call pc_controller "
        f"(action=time or action=date) and speak that tool result — never guess.\n\n"
    )
    brief_str = session_brief.format_for_prompt()

    parts = [time_ctx]
    if mem_str:
        parts.append(mem_str)
    if brief_str:
        parts.append(brief_str)
    parts.append(sys_prompt)
    system_instruction = "\n".join(parts)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[{"function_declarations": _tool_declarations()}],
        temperature=0.7,
    )

    chat_session = client.chats.create(model="gemini-3.1-flash-lite-preview", config=config)
    return chat_session


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_authorized(user_id):
        await update.message.reply_text(
            f"Unauthorized.\nYour Telegram User ID is: `{user_id}`.\n"
            "Add it to `telegram_allowed_users` in `config/api_keys.json`."
        )
        return

    query = update.message.text
    if not query:
        return

    status_message = await update.message.reply_text("🤔 Thinking...")

    try:
        session = get_chat_session()
        response = await asyncio.to_thread(session.send_message, query)

        # Loop to handle function/tool calls requested by the model
        while response.function_calls:
            from google.genai import types

            for function_call in response.function_calls:
                name = function_call.name
                args = dict(function_call.args or {})

                await status_message.edit_text(f"🔧 Executing `{name}`...")
                logger.info(f"[Telegram Tool] Executing {name} with args {args}")

                # Execute tool using dispatch
                def run_tool():
                    # Special check for agent_task submit so it doesn't block
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

                        # We define a dummy speak function for telegram updates
                        def tg_speak(msg):
                            logger.info(f"[Agent Task Msg] {msg}")

                        task_id = get_queue().submit(
                            goal=args.get("goal", ""), priority=priority, speak=tg_speak
                        )
                        return f"Task started (ID: {task_id})."

                    import agent.tool_registry as tool_registry

                    return tool_registry.dispatch(name, parameters=args)

                result = await asyncio.to_thread(run_tool)

                # Send the function response back to the model
                response = await asyncio.to_thread(
                    session.send_message,
                    types.Part.from_function_response(
                        name=name, response={"result": result}
                    ),
                )

        # Send final text response
        bot_response = response.text or "Done."
        await status_message.edit_text(bot_response)

    except Exception as e:
        logger.error(f"Error in conversation: {e}")
        await status_message.edit_text(f"❌ Error: {e}")


_TELEGRAM_LOCK_FILE = Path.home() / ".lucas" / "telegram_bot.lock"


def _acquire_lock() -> bool:
    """Try to acquire a PID lock file. Returns True if this is the only instance."""
    _TELEGRAM_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if _TELEGRAM_LOCK_FILE.exists():
            pid = int(_TELEGRAM_LOCK_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                logger.warning("Telegram bot already running (PID %d). Skipping.", pid)
                return False
            except (OSError, ProcessLookupError):
                pass
        _TELEGRAM_LOCK_FILE.write_text(str(os.getpid()))
        atexit.register(lambda: _TELEGRAM_LOCK_FILE.unlink(missing_ok=True))
        return True
    except Exception as exc:
        logger.warning("Telegram lock check failed: %s", exc)
        return True


def start_in_background():
    if not _TELEGRAM_AVAILABLE:
        logger.warning(
            "Telegram Bot is disabled: python-telegram-bot is not installed."
        )
        return

    token = get_telegram_token()
    if not token:
        logger.warning(
            "Telegram Bot is disabled: telegram_bot_token is not configured."
        )
        return

    if not _acquire_lock():
        return

    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        application = Application.builder().token(token).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        async def run_async():
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            logger.info("Telegram Bot is online and polling.")
            while True:
                await asyncio.sleep(3600)

        try:
            loop.run_until_complete(run_async())
        except Conflict as e:
            logger.warning(
                "Telegram bot conflict (another instance running?) — shutting down: %s",
                e,
            )
        except (NetworkError, TimedOut, ConnectionError, OSError) as e:
            logger.warning(
                "Telegram bot network issue — will retry on next startup: %s",
                e,
            )
        except Exception as e:
            logger.error("Telegram bot crashed: %s", e)
        finally:
            try:
                loop.run_until_complete(application.shutdown())
            except Exception:
                pass
            loop.close()

    threading.Thread(target=run_bot, daemon=True).start()


def main():
    if not _TELEGRAM_AVAILABLE:
        print(
            "Error: python-telegram-bot is not installed. Please run `pip install python-telegram-bot`"
        )
        sys.exit(1)

    token = get_telegram_token()
    if not token:
        print("Error: telegram_bot_token is not configured in config/api_keys.json")
        sys.exit(1)

    # Initialize Telegram application
    application = Application.builder().token(token).build()

    # Add command and message handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("🤖 Starting Lucas Telegram Bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
