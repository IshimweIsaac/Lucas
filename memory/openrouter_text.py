"""OpenRouter chat completions (OpenAI-compatible) using config/agent_keys.json."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from agent.key_manager import get_key_manager
from core.logger import get_logger

logger = get_logger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _normalize_model(model: str) -> str:
    """Normalize OpenRouter model id; keep full id as-is."""
    name = (model or "").strip()
    if name.startswith("openrouter/"):
        name = name[len("openrouter/") :]
    if not name:
        return "openai/gpt-4o-mini"
    return name


def generate_text_openrouter(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
    timeout: int = 120,
) -> str:
    """One-shot chat completion via OpenRouter."""
    api_key = get_key_manager().get_key("openrouter")
    if not api_key:
        raise RuntimeError(
            'No OpenRouter API key. Add keys to config/agent_keys.json under "openrouter".'
        )

    messages: list[dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": contents})

    payload = {
        "model": _normalize_model(model),
        "messages": messages,
        "temperature": 0.15,
    }
    req = urllib.request.Request(
        _OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/IshimweIsaac/Lucas",
            "X-Title": "Lucas",
            "User-Agent": "Lucas/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter returned no choices.")
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise ValueError("OpenRouter returned an empty response.")
    return text


def fetch_models(timeout: int = 30) -> list[dict]:
    """Fetch available models from OpenRouter.

    No auth required. Returns list of model dicts from the ``data`` field.
    Raises RuntimeError on HTTP errors.
    """
    req = urllib.request.Request(
        _MODELS_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Lucas/1.0",
            "HTTP-Referer": "https://github.com/IshimweIsaac/Lucas",
            "X-Title": "Lucas",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc
    data = raw.get("data")
    if isinstance(data, list):
        return data
    return []


def get_model_pricing(model_id: str, timeout: int = 30) -> dict | None:
    """Return model dict for *model_id* or None if not found."""
    models = fetch_models(timeout=timeout)
    target = (model_id or "").strip()
    if target.startswith("openrouter/"):
        target = target[len("openrouter/") :]
    for entry in models:
        entry_id = str(entry.get("id") or "").strip()
        if entry_id == target:
            return entry
    return None
