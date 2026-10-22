"""Multi-model coding router: primary Gemini (voice key), Groq circuit-breaker fallback."""

from __future__ import annotations

import threading
import time

from core.logger import get_logger
from memory import gemini_text, groq_text

# OpenRouter is available via memory.openrouter_text directly; optional import
# keeps the router importable even if the module is absent in stripped installs.
try:
    from memory import openrouter_text
except ImportError:  # pragma: no cover
    openrouter_text = None  # type: ignore[assignment]

logger = get_logger(__name__)

GROQ_FALLBACK_MODEL: str = "gpt-oss-120b"
_FAIL_THRESHOLD: int = 3  # consecutive failures before a leg is skipped
_COOLDOWN_SEC: int = 300  # how long an open breaker stays open

_health_lock = threading.Lock()
# Symmetric health state; restart clears it (no persistence by design).
_health: dict[str, dict[str, float | int]] = {
    "gemini": {"fails": 0, "open_until": 0.0},
    "groq": {"fails": 0, "open_until": 0.0},
}
_last_provider: str = ""


def _record_failure(provider: str) -> None:
    """Count one failure; open the breaker once the threshold is reached."""
    with _health_lock:
        state = _health[provider]
        state["fails"] += 1
        if state["fails"] >= _FAIL_THRESHOLD:
            state["open_until"] = time.time() + _COOLDOWN_SEC


def _record_success(provider: str) -> None:
    """Reset breaker state after a healthy call."""
    with _health_lock:
        state = _health[provider]
        state["fails"] = 0
        state["open_until"] = 0.0


def _is_open(provider: str) -> bool:
    """True while the provider's breaker is open (leg must be skipped)."""
    with _health_lock:
        return time.time() < float(_health[provider]["open_until"])


def last_provider() -> str:
    """Provider that served the most recent request ("gemini"/"groq"; "" before first)."""
    return _last_provider


def generate_via_openrouter(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
) -> str:
    """Direct OpenRouter call (bypasses Gemini/Groq routing)."""
    if openrouter_text is None:  # pragma: no cover
        raise RuntimeError("openrouter_text module not available")
    return openrouter_text.generate_text_openrouter(
        model, contents, system_instruction=system_instruction
    )


def reset_health(provider: str | None = None) -> None:
    """Clear router state for one provider or both. Test hook / manual clear.

    A full reset (provider=None) restores fresh-restart state, including
    ``last_provider``; a per-provider reset only clears that leg's breaker.
    """
    global _last_provider
    names = [provider] if provider else ["gemini", "groq"]
    with _health_lock:
        for name in names:
            if name in _health:
                _health[name] = {"fails": 0, "open_until": 0.0}
        if provider is None:
            _last_provider = ""


def generate_routed(
    model: str,
    contents: str,
    *,
    system_instruction: str | None = None,
) -> str:
    """Route a coding LLM request: Gemini first, Groq fallback.

    Args:
        model: Requested model id (used only on the Gemini leg).
        contents: User prompt text.
        system_instruction: Optional system prompt passed to both legs.

    Returns:
        The generated text from whichever leg served the request.

    Raises:
        RuntimeError: Only when BOTH legs fail; the message lists both errors.
    """
    global _last_provider
    gemini_error: BaseException | None = None
    groq_error: BaseException | None = None
    gemini_open = _is_open("gemini")
    groq_open = _is_open("groq")

    if not gemini_open:
        try:
            text = gemini_text.generate_text(
                model, contents, system_instruction=system_instruction
            )
            _record_success("gemini")
            _last_provider = "gemini"
            logger.info("coding request served by %s (model=%s)", "gemini", model)
            return text
        except Exception as exc:
            gemini_error = exc
            _record_failure("gemini")
            logger.warning("Gemini leg failed (%s); falling back to Groq", exc)
    else:
        logger.warning("Gemini breaker open; skipping primary leg")

    if not groq_open:
        try:
            text = groq_text.generate_text_groq(
                GROQ_FALLBACK_MODEL,
                contents,
                system_instruction=system_instruction,
            )
            _record_success("groq")
            _last_provider = "groq"
            logger.info(
                "coding request served by %s (model=%s)", "groq", GROQ_FALLBACK_MODEL
            )
            return text
        except Exception as exc:
            groq_error = exc
            _record_failure("groq")
            logger.warning("Groq leg failed (%s); no further fallback", exc)
    else:
        logger.warning("Groq breaker open; skipping fallback leg")

    raise RuntimeError(
        "Coding router: all legs failed "
        f"(gemini -> {gemini_error or 'breaker open'}; "
        f"groq -> {groq_error or 'breaker open'})"
    )
