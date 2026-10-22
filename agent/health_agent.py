from core.logger import get_logger
from memory.gemini_text import generate_text_with_agent_key

logger = get_logger(__name__)

def summarize_health(metrics: dict) -> str:
    """Translate raw metrics into a human-readable markdown summary."""
    prompt = f"Summarize the following system metrics into a concise, human-readable markdown report:\n\n{metrics}"
    
    try:
        return generate_text_with_agent_key(
            model="gemini/gemini-3.1-flash-lite-preview",
            contents=prompt,
            system_instruction="You are a system health monitor. Provide clear, actionable insights from metrics."
        )
    except Exception as e:
        logger.error(f"Failed to generate health summary: {e}")
        return "Unable to generate health summary at this time."
