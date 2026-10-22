"""Shared Gemini text generation via google.genai (not deprecated generativeai)."""

from __future__ import annotations

from pathlib import Path

from memory.config_manager import get_gemini_key, get_genai_client


def response_text(response) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", None)
    if text:
        return text.strip()
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    parts = getattr(candidates[0].content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        if hasattr(part, "text") and part.text:
            chunks.append(part.text)
    return "".join(chunks).strip()


def _client_for_api_key(api_key: str):
    from google import genai

    return genai.Client(api_key=api_key)


def generate_text_with_agent_key(
    model: str,
    contents: str,
    *,
    provider: str = "gemini",
    system_instruction: str | None = None,
) -> str:
    """
    Gemini text using ``config/agent_keys.json`` (round-robin).

    Falls back to voice ``api_keys.json`` if no agent keys exist for *provider*.
    """
    from agent.key_manager import get_key_manager

    km = get_key_manager()
    api_key = km.get_key(provider) if km.has_keys(provider) else ""
    if not api_key:
        api_key = get_gemini_key()
    if not api_key:
        raise RuntimeError(
            "No Gemini API key. Add keys to config/agent_keys.json (agents) "
            "or config/api_keys.json (voice)."
        )

    client = _client_for_api_key(api_key)
    config = {"system_instruction": system_instruction} if system_instruction else None
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    text = response_text(response)
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def generate_text(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
) -> str:
    client = get_genai_client()
    config = {"system_instruction": system_instruction} if system_instruction else None
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    text = response_text(response)
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def generate_with_bytes(
    model: str,
    prompt: str,
    data: bytes,
    *,
    mime_type: str,
) -> str:
    from google.genai import types

    client = get_genai_client()
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime_type),
            prompt,
        ],
    )
    text = response_text(response)
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def generate_multimodal(
    model: str,
    prompt: str,
    image_path: str | Path,
    *,
    mime_type: str | None = None,
) -> str:
    """Text + image via google.genai."""
    from google.genai import types

    path = Path(image_path)
    suffix = path.suffix.lower()
    mime = mime_type or {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
    data = path.read_bytes()
    client = get_genai_client()
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime),
            prompt,
        ],
    )
    text = response_text(response)
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text
