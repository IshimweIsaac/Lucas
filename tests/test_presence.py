from __future__ import annotations

from core import presence_status


def test_format_short():
    s = presence_status.format_short()
    assert "wake=" in s
