"""Groq chat completions (OpenAI-compatible) using config/agent_keys.json."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from agent.key_manager import get_key_manager

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _normalize_model(model: str) -> str:
    name = (model or "gpt-oss-120b").strip()
    if name.startswith("groq/"):
        name = name[5:]
    if not name.startswith("openai/"):
        name = f"openai/{name}"
    return name


def generate_text_groq(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
    timeout: int = 120,
) -> str:
    """One-shot chat completion via Groq."""
    api_key = get_key_manager().get_key("groq")
    if not api_key:
        raise RuntimeError(
            "No Groq API key. Add keys to config/agent_keys.json under \"groq\"."
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
        _GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Lucas/1.0 (Groq API client)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Groq HTTP {exc.code}: {body}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Groq returned no choices.")
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise ValueError("Groq returned an empty response.")
    return text
