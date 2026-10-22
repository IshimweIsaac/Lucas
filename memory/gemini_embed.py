"""Shared Gemini embeddings via google.genai."""

from __future__ import annotations

from memory.config_manager import get_genai_client

_EMBED_MODEL = "text-embedding-004"


def embed_text(text: str) -> list[float]:
    """Embed *text* into a float vector using text-embedding-004."""
    response = get_genai_client().models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
    )
    embeddings = response.embeddings or []
    if not embeddings or not embeddings[0].values:
        raise ValueError("Gemini returned no embeddings.")
    return list(embeddings[0].values)
