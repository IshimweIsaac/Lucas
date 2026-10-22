"""Tests for SummarizerAgent (mocked API)."""

from __future__ import annotations

from unittest.mock import patch

from agent.summarizer_agent import SummarizerAgent, run_summarize


def test_summarize_calls_gemini_with_max_chars():
    with patch("agent.summarizer_agent.get_key_manager") as mock_km:
        mock_km.return_value.has_keys.return_value = True
        agent = SummarizerAgent(model="gemini-3.1-flash-lite")
        with patch("agent.summarizer_agent.generate_text_with_agent_key") as mock_gen:
            mock_gen.return_value = "Short summary."

            result = agent.summarize("Long text to summarize", max_chars=500)

            assert result.ok
            assert result.summary == "Short summary."
            mock_gen.assert_called_once()
            assert "500" in mock_gen.call_args.args[1]


def test_run_summarize_helper():
    with patch("agent.summarizer_agent.SummarizerAgent") as mock_cls:
        mock_cls.return_value.summarize.return_value.summary = "Done."
        assert run_summarize("hello", max_chars=100) == "Done."
        mock_cls.return_value.summarize.assert_called_once_with("hello", max_chars=100)
