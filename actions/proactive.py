"""Proactive companion tool — the model-facing surface of the proactive engine.

Actions: status | on_your_mind | dismiss | history | configure | budget |
research_topic. The on_your_mind path never triggers autonomous generation;
research_topic is a manual, never-throttled user request.
"""

from __future__ import annotations

TOOL_SCHEMA = {
    "name": "proactive",
    "description": (
        "Proactive companion engine: status, on_your_mind, dismiss, history, "
        "configure, budget, research_topic. Review or adjust Lucas proactive "
        "engagement."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "status|on_your_mind|dismiss|history|configure|budget|"
                    "research_topic"
                ),
            },
            "entry_id": {
                "type": "STRING",
                "description": "Engagement id to dismiss",
            },
            "topic": {
                "type": "STRING",
                "description": "Topic for research_topic",
            },
            "settings": {
                "type": "OBJECT",
                "description": "Config changes for configure",
            },
        },
        "required": ["action"],
    },
}


def proactive(*, parameters: dict, player=None) -> str:
    """Execute the proactive tool action."""
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()

    from core import proactive as engine

    if action == "status":
        return engine.status()
    if action == "on_your_mind":
        return engine.on_your_mind()
    if action == "history":
        return engine.history(limit=10)
    if action == "budget":
        return engine.budget()
    if action == "dismiss":
        entry_id = (params.get("entry_id") or "").strip()
        if not entry_id:
            return "Please provide an entry_id to dismiss, sir."
        return engine.dismiss(entry_id)
    if action == "configure":
        return engine.configure(params.get("settings") or {})
    if action == "research_topic":
        topic = (params.get("topic") or "").strip()
        if not topic:
            return "Please provide a topic, sir."
        return engine.research_now(topic, manual=True)
    return f"Unknown action: {action}"