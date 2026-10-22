from __future__ import annotations

import json
from unittest.mock import patch
from memory.config_manager import get_telegram_token, get_telegram_allowed_users
import telegram_bot

def test_telegram_config(tmp_path, monkeypatch):
    # Setup dummy keys file
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "api_keys.json"
    
    mock_config = {
        "gemini_api_key": "dummy-gemini-key-long-enough-12345",
        "telegram_bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "telegram_allowed_users": [123456789, "987654321"]
    }
    config_file.write_text(json.dumps(mock_config))
    
    # Mock base directory in config_manager
    monkeypatch.setattr("memory.config_manager.CONFIG_FILE", config_file)
    monkeypatch.setattr("memory.config_manager.CONFIG_DIR", config_dir)
    
    # Reload config load function behavior
    assert get_telegram_token() == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    assert get_telegram_allowed_users() == [123456789, 987654321]

@patch("telegram_bot.get_telegram_allowed_users")
def test_check_authorized(mock_allowed):
    mock_allowed.return_value = [11111, 22222]
    
    assert telegram_bot.check_authorized(11111) is True
    assert telegram_bot.check_authorized(33333) is False
    
    # Case with empty allowed users
    mock_allowed.return_value = []
    assert telegram_bot.check_authorized(11111) is False
