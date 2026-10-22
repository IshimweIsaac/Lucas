from __future__ import annotations

from unittest.mock import patch
from agent.error_handler import analyze_error, ErrorDecision

def test_analyze_error_max_attempts():
    step = {"step": 1, "tool": "web_search", "description": "Search"}
    result = analyze_error(step, "Some error", attempt=3, max_attempts=3)
    
    assert result["decision"] == ErrorDecision.REPLAN
    assert result["max_retries"] == 0
    assert "Failed 3 times" in result["reason"]

@patch("memory.gemini_text.generate_text")
def test_analyze_error_critical_skip(mock_generate):
    mock_generate.return_value = '{"decision": "skip", "reason": "Not important"}'

    # Step is critical
    step = {"step": 1, "critical": True, "tool": "web_search", "description": "Search"}
    result = analyze_error(step, "Error", attempt=1)
    
    # It should upgrade SKIP to REPLAN because critical=True
    assert result["decision"] == ErrorDecision.REPLAN
    assert "critical" in result["user_message"].lower()

@patch("memory.gemini_text.generate_text")
def test_analyze_error_parsing_failure(mock_generate):
    mock_generate.return_value = "invalid json output"

    step = {"step": 1, "tool": "web_search"}
    result = analyze_error(step, "Error", attempt=1)
    
    # On parse failure, defaults to REPLAN
    assert result["decision"] == ErrorDecision.REPLAN
    assert result["max_retries"] == 1
