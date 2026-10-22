from __future__ import annotations

from unittest.mock import MagicMock, patch

from memory.gemini_text import generate_text, response_text


def test_response_text_from_text_attr():
    r = MagicMock()
    r.text = "  hello  "
    assert response_text(r) == "hello"


@patch("memory.gemini_text.get_genai_client")
def test_generate_text(mock_client):
    mock_response = MagicMock()
    mock_response.text = "ok"
    mock_client.return_value.models.generate_content.return_value = mock_response

    out = generate_text("gemini-3.1-flash-lite", "ping", system_instruction="sys")
    assert out == "ok"
    call_kw = mock_client.return_value.models.generate_content.call_args.kwargs
    assert call_kw["model"] == "gemini-3.1-flash-lite"
    assert call_kw["config"]["system_instruction"] == "sys"
