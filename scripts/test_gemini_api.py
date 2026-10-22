#!/usr/bin/env python3
"""Quick check that config/api_keys.json works with Gemini."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.config_manager import get_genai_client, is_configured


def main() -> int:
    if not is_configured():
        print("❌ No API key in config/api_keys.json")
        return 1

    client = get_genai_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents="Reply with exactly: Lucas API OK",
    )
    print("✅", (response.text or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
