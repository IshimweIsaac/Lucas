from __future__ import annotations

from unittest.mock import patch
from agent.planner import create_plan, _fallback_plan

def test_fallback_plan():
    plan = _fallback_plan("Do something")
    assert plan["goal"] == "Do something"
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["tool"] == "web_search"
    assert plan["steps"][0]["critical"] is True

@patch("memory.gemini_text.generate_text")
def test_create_plan_valid_json(mock_generate):
    mock_generate.return_value = '''
    {
      "goal": "Test goal",
      "steps": [
        {
          "step": 1,
          "tool": "web_search",
          "description": "Search test",
          "parameters": {"query": "test"},
          "critical": true
        }
      ]
    }
    '''

    plan = create_plan("Test goal")
    assert plan["goal"] == "Test goal"
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["tool"] == "web_search"

@patch("memory.gemini_text.generate_text")
def test_create_plan_generated_code_replaced(mock_generate):
    mock_generate.return_value = '''
    {
      "goal": "Hack",
      "steps": [
        {
          "step": 1,
          "tool": "generated_code",
          "description": "Write a python script",
          "parameters": {},
          "critical": true
        }
      ]
    }
    '''

    plan = create_plan("Hack")
    
    # The planner should sanitize generated_code into web_search
    assert plan["steps"][0]["tool"] == "web_search"
    assert "query" in plan["steps"][0]["parameters"]
