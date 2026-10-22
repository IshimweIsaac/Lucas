import json
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()

    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["gemini_api_key"] = gemini_api_key.strip()

    CONFIG_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )

def load_api_keys() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def get_telegram_token() -> str | None:
    return load_api_keys().get("telegram_bot_token")

def get_tavily_keys() -> list[str]:
    data = load_api_keys()
    # Support both array and legacy single-key config
    keys = data.get("tavily_api_keys", [])
    if isinstance(keys, list) and keys:
        return [k for k in keys if k]
    single = data.get("tavily_api_key")
    return [single] if single else []

def get_telegram_allowed_users() -> list[int]:
    val = load_api_keys().get("telegram_allowed_users")
    if isinstance(val, list):
        return [int(x) for x in val if str(x).isdigit()]
    elif val is not None:
        try:
            return [int(val)]
        except (ValueError, TypeError):
            pass
    return []

def is_configured() -> bool:

    key = get_gemini_key()
    return bool(key and len(key) > 15)


SETTINGS_FILE = CONFIG_DIR / "settings.json"


def get_setting(key: str, default: object = None) -> object:
    """Read a user setting from config/settings.json, falling back to *default*."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data.get(key, default)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


_genai_client = None


def get_genai_client():
    """
    Reuse one google.genai Client. Do not chain Client(...).models.* inline —
    the client can close before the request finishes.
    """
    global _genai_client
    key = get_gemini_key()
    if not key:
        raise RuntimeError(
            "Gemini API key not configured. Add it via setup or config/api_keys.json"
        )
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(api_key=key)
    return _genai_client